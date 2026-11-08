"""The fetched tables, the report and the summary (internal)."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

from tr_news_scraper._copies import copy_groups
from tr_news_scraper._extract import Extracted
from tr_news_scraper._fetch import Fetched, FetchRun
from tr_news_scraper._table import day_series, http_counts, string_series, time_series
from tr_news_scraper.matching import KeywordQuery, fold
from tr_news_scraper.outlets import Outlet
from tr_news_scraper.outlets._dates import ISTANBUL

if TYPE_CHECKING:
    import pandas as pd

    from tr_news_scraper._http import HostStats

ADDED_COLUMNS = (
    "published",
    "author",
    "text",
    "text_matched",
    "copy_group",
    "fetched_at",
    "error",
)
FETCH_COUNTS = ("articles", "downloaded", "cached", "failed", "outside", "undated", "copies")
HTTP_COUNTS = ("requests", "cache_hits", "retries", "errors")
FETCH_REPORT_COLUMNS = ("outlet", "name", *FETCH_COUNTS, "detail", *HTTP_COUNTS, "robots_override")
COPIES_NOTE = "{count:,} articles are copies of a story another article also carries (copy_group)."
MAX_DETAILS = 3
NOT_READ = "it wasn't read"
_SEPARATOR = re.compile(r"\s+[-|–—]\s+")


def clean_headline(title: str | None, outlet_name: str) -> str | None:
    """A page's headline without a trailing part that names the outlet, like "… - Sözcü
    Gazetesi" or "… | STAR". The outlet is recognized by the first word of its name."""
    if title is None:
        return None
    separators = list(_SEPARATOR.finditer(title))
    if not separators:
        return title
    last = separators[-1]
    head = title[: last.start()].strip()
    if head and fold(outlet_name.split()[0]) in fold(title[last.end() :]):
        return head
    return title


@dataclass(frozen=True, eq=False, repr=False)
class FetchResult:
    """What ``fetch()`` read: the articles, the rows whose page dates them outside the range,
    and a report on every outlet. ``print(result)`` shows a short summary."""

    articles: pd.DataFrame
    """The rows in the range, and those whose page gives no date or couldn't be read."""
    outside: pd.DataFrame
    """The rows whose page dates them outside [start, end)."""
    report: pd.DataFrame
    keywords: tuple[str, ...]
    start: date | None
    end: date | None
    """The day after the last day of the range."""
    outlets: tuple[Outlet, ...]
    fetched_at: datetime
    """When the fetch ran, in Europe/Istanbul."""
    version: str

    def __repr__(self) -> str:
        return f"FetchResult({self._headline()})"

    def __str__(self) -> str:
        read = self.articles[self.articles["error"].isna()]
        names = [str(name) for name in self.report["name"]]
        counts = [f"{int((read['outlet'] == outlet).sum()):,}" for outlet in self.report["outlet"]]
        name_width = max(map(len, names), default=0)
        count_width = max(map(len, counts), default=0)
        lines = [self._headline()]
        for name, count, failed, detail in zip(
            names, counts, self.report["failed"], self.report["detail"], strict=True
        ):
            note = f"{int(failed):,} failed: {detail}" if failed else ""
            lines.append(f"  {name:<{name_width}}  {count:>{count_width}}  {note}".rstrip())
        copies = int(self.articles["copy_group"].notna().sum())
        if copies:
            lines.append(COPIES_NOTE.format(count=copies))
        return "\n".join(lines)

    def _headline(self) -> str:
        errors = self.articles["error"]
        read, failed = int(errors.isna().sum()), int(errors.notna().sum())
        parts = [f"{read:,} {_plural(read, 'article')} read"]
        if self.start is not None and self.end is not None:
            parts.append(f"{len(self.outside):,} outside the range")
        parts.append(f"{failed:,} failed")
        summary = ", ".join(parts)
        scope = [", ".join(self.keywords)] if self.keywords else []
        if self.start is not None and self.end is not None:
            last = self.end - timedelta(days=1)
            scope.append(str(self.start) if last == self.start else f"{self.start} to {last}")
        return f"{', '.join(scope)}: {summary}" if scope else summary


def build_fetch_result(
    articles: pd.DataFrame,
    runs: Sequence[FetchRun],
    *,
    keywords: Sequence[str],
    start: date | None,
    end: date | None,
    outlets: Sequence[Outlet],
    fetched_at: datetime,
    version: str,
    stats: Mapping[str, HostStats],
) -> FetchResult:
    """Add what every page said to ``articles``, fill empty days and titles, set the rows dated
    outside [start, end) apart, and report on each outlet (F5, F6, D1, D2, D10)."""
    import pandas as pd

    table = articles.reset_index(drop=True).copy()
    results: dict[int, Fetched] = {}
    for run in runs:
        results.update(run.results)
    rows = [results.get(i, Fetched(Extracted(error=NOT_READ))) for i in range(len(table))]
    found = [row.extracted for row in rows]
    days = [None if f.published is None else f.published.astimezone(ISTANBUL).date() for f in found]
    texts = [f.text for f in found]
    names = {outlet.id: outlet.name for outlet in outlets}

    if "day" not in table:
        table["day"] = day_series([None] * len(table))
    table["day"] = table["day"].fillna(day_series(days))
    if "title" not in table:
        table["title"] = string_series([None] * len(table))
    headlines = [
        clean_headline(f.title, names.get(str(outlet), str(outlet)))
        for f, outlet in zip(found, table["outlet"], strict=True)
    ]
    table["title"] = table["title"].astype("string").fillna(string_series(headlines))

    table["published"] = time_series([f.published for f in found])
    table["author"] = string_series([f.author for f in found])
    table["text"] = string_series(texts)
    table["text_matched"] = string_series(_text_matches(texts, keywords))
    table["copy_group"] = pd.Series(copy_groups(texts, days), dtype="Int64")
    table["fetched_at"] = time_series([row.fetched_at for row in rows])
    table["error"] = string_series([f.error for f in found])

    outside = pd.Series(
        [
            day is not None and start is not None and end is not None and not start <= day < end
            for day in days
        ],
        dtype="bool",
    )
    return FetchResult(
        articles=table[~outside].reset_index(drop=True),
        outside=table[outside].reset_index(drop=True),
        report=_report(table, outside, runs, stats),
        keywords=tuple(keywords),
        start=start,
        end=end,
        outlets=tuple(outlets),
        fetched_at=fetched_at,
        version=version,
    )


def _text_matches(texts: Sequence[str | None], keywords: Sequence[str]) -> list[str]:
    """The keywords found in each text, in query order (F6); empty when none."""
    if not keywords:
        return [""] * len(texts)
    query = KeywordQuery(keywords)
    matches = []
    for text in texts:
        found = {match.keyword for match in query.match(text=text)} if text else set()
        matches.append(", ".join(keyword for keyword in query.keywords if keyword in found))
    return matches


def _report(
    table: pd.DataFrame,
    outside: pd.Series,
    runs: Sequence[FetchRun],
    stats: Mapping[str, HostStats],
) -> pd.DataFrame:
    import pandas as pd

    records = []
    for run in runs:
        mine = table["outlet"] == run.outlet.id
        errors = Counter(str(error) for error in table.loc[mine, "error"].dropna())
        records.append(
            {
                "outlet": run.outlet.id,
                "name": run.outlet.name,
                "articles": int(mine.sum()),
                "downloaded": run.downloaded,
                "cached": run.cached,
                "failed": run.failed,
                "outside": int((mine & outside).sum()),
                "undated": int((mine & table["error"].isna() & table["published"].isna()).sum()),
                "copies": int((mine & table["copy_group"].notna()).sum()),
                "detail": _detail(errors),
                **http_counts(run.outlet, stats),
            }
        )
    columns: dict[str, pd.Series] = {}
    for name in FETCH_REPORT_COLUMNS:
        values = [record[name] for record in records]
        if name in (*FETCH_COUNTS, *HTTP_COUNTS):
            columns[name] = pd.Series(values, dtype="int64")
        elif name == "robots_override":
            columns[name] = pd.Series(values, dtype="bool")
        else:
            columns[name] = pd.Series(values, dtype="string")
    return pd.DataFrame(columns)


def _detail(errors: Counter[str]) -> str:
    """The most common reasons with their counts, e.g. "3 × robots.txt disallows it"."""
    common = [f"{count:,} × {reason}" for reason, count in errors.most_common()]
    if len(common) > MAX_DETAILS:
        common = [*common[:MAX_DETAILS], f"and {len(common) - MAX_DETAILS} more"]
    return "; ".join(common)


def _plural(count: int, word: str) -> str:
    return word if count == 1 else f"{word}s"
