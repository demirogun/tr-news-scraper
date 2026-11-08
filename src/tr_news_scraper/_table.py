"""The search result's rows and tables (internal).

Each outlet's run produces plain ``Row`` records. Only the functions that build DataFrames import
pandas, so ``import tr_news_scraper`` stays light.
"""

from __future__ import annotations

import html
import unicodedata
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Final
from urllib.parse import urlsplit, urlunsplit

from tr_news_scraper.outlets import Month, Outlet, SiteSearch
from tr_news_scraper.outlets._dates import ISTANBUL
from tr_news_scraper.outlets._model import Gap
from tr_news_scraper.outlets._search import query_text

if TYPE_CHECKING:
    import pandas as pd

    from tr_news_scraper._http import HostStats

ARTICLE_COLUMNS = (
    "outlet",
    "month",
    "day",
    "title",
    "url",
    "matched",
    "reasons",
    "lastmod",
    "source",
)
GAP_COLUMNS = ("outlet", "reason", "month", "keyword", "detail", "url")
REPORT_TEXT = ("outlet", "name", "method", "status", "coverage")
REPORT_COUNTS = ("articles", "candidates", "trimmed", "unconfirmed")
HTTP_COUNTS = ("requests", "cache_hits", "retries", "errors")
REPORT_COLUMNS = (
    *REPORT_TEXT,
    *REPORT_COUNTS,
    "dates",
    "detail",
    *HTTP_COUNTS,
    "robots_override",
)
DAY_DTYPE: Final = "datetime64[ns]"
TIME_DTYPE: Final = "datetime64[ns, Europe/Istanbul]"
DATES_NOTE = (
    "Sitemap outlets are dated to the month; fetch() reads each article's publication time."
)
FAILURE_REASONS = frozenset({"robots", "blocked", "failed"})
COVERAGE_REASONS = frozenset({"before-archive", "after-archive", "not-in-archive", "window"})
MAX_DETAILS = 3

_DEFAULT_PORTS = {"https": 443, "http": 80}


@dataclass(frozen=True, slots=True)
class Row:
    """One matching article, before the table is built."""

    outlet: str
    url: str
    month: Month
    matched: tuple[str, ...]
    """The keywords that matched, in query order."""
    reasons: tuple[str, ...]
    """Every match's reason: title first, then URL."""
    source: str
    title: str | None = None
    day: date | None = None
    lastmod: datetime | None = None


@dataclass(slots=True)
class OutletRun:
    """What one outlet's scan produced: its rows, what it left out and why, and its gaps."""

    outlet: Outlet
    rows: list[Row] = field(default_factory=list)
    candidates: int = 0
    """Archive entries in the range's months, or search results in the range."""
    trimmed: int = 0
    """Matching entries left out by their dates (S4)."""
    unconfirmed: int = 0
    """Search results whose headline and URL name no keyword (S3)."""
    gaps: list[Gap] = field(default_factory=list)
    failure: str | None = None
    """Why nothing could be read, when the outlet failed."""


def clean_url(url: str) -> str:
    """Lowercase the scheme and host, and drop the default port and the fragment (S5).

    The path and the query are kept exactly. A URL whose port can't be read is only stripped.
    """
    text = url.strip()
    if _already_clean(text):
        return text
    parts = urlsplit(text)
    try:
        port = parts.port
    except ValueError:
        return text
    scheme = parts.scheme.lower()
    host = parts.hostname or ""
    netloc = host if port is None or port == _DEFAULT_PORTS.get(scheme) else f"{host}:{port}"
    return urlunsplit((scheme, netloc, parts.path, parts.query, ""))


def _already_clean(url: str) -> bool:
    """The usual case, checked without parsing: HTTPS, a lowercase host with no port or user,
    and no fragment."""
    if not url.startswith("https://") or "#" in url:
        return False
    end = url.find("/", 8)
    host = url[8:] if end == -1 else url[8:end]
    return host == host.lower() and ":" not in host and "@" not in host


def clean_title(title: str | None) -> str | None:
    """Decode leftover HTML entities, collapse whitespace and normalize to NFC (S5). Some
    sitemaps escape their titles twice. An empty title becomes ``None``."""
    if title is None:
        return None
    text = unicodedata.normalize("NFC", " ".join(html.unescape(title).split()))
    return text or None


def clean_lastmod(lastmod: datetime | None) -> datetime | None:
    """The last-edit time in Europe/Istanbul, so the table's column has one time zone."""
    return None if lastmod is None else lastmod.astimezone(ISTANBUL)


def merge(rows: Iterable[Row], keywords: Sequence[str], order: Mapping[str, int]) -> list[Row]:
    """One row per URL (S6), sorted by month, outlet, day and URL (S7).

    A URL found more than once keeps the earliest month, the first title, day and last-edit time
    found, and every keyword and reason, in query order and without repeats. ``order`` gives each
    outlet's position in the search.
    """
    by_url: dict[str, Row] = {}
    for row in rows:
        kept = by_url.get(row.url)
        if kept is None:
            by_url[row.url] = row
        elif _place(row, order) < _place(kept, order):
            by_url[row.url] = _combine(row, kept, keywords)
        else:
            by_url[row.url] = _combine(kept, row, keywords)
    return sorted(
        by_url.values(),
        key=lambda row: (
            *_place(row, order),
            row.day is None,
            row.day or date.min,
            row.url,
        ),
    )


def _place(row: Row, order: Mapping[str, int]) -> tuple[int, int, int]:
    """Where a row sorts first: its month, then its outlet's position. Plain integers compare
    much faster than ``Month`` objects."""
    return (row.month.year, row.month.month, order[row.outlet])


def _combine(kept: Row, other: Row, keywords: Sequence[str]) -> Row:
    found = set(kept.matched) | set(other.matched)
    return replace(
        kept,
        matched=tuple(keyword for keyword in keywords if keyword in found),
        reasons=tuple(dict.fromkeys((*kept.reasons, *other.reasons))),
        title=kept.title if kept.title is not None else other.title,
        day=kept.day if kept.day is not None else other.day,
        lastmod=kept.lastmod if kept.lastmod is not None else other.lastmod,
    )


def articles_frame(rows: Sequence[Row]) -> pd.DataFrame:
    """The article table: the spec's columns and dtypes, on pandas 2 and 3 alike."""
    import pandas as pd

    return pd.DataFrame(
        {
            "outlet": string_series([row.outlet for row in rows]),
            "month": string_series([str(row.month) for row in rows]),
            "day": day_series([row.day for row in rows]),
            "title": string_series([row.title for row in rows]),
            "url": string_series([row.url for row in rows]),
            "matched": string_series([", ".join(row.matched) for row in rows]),
            "reasons": string_series(["; ".join(row.reasons) for row in rows]),
            "lastmod": time_series([row.lastmod for row in rows]),
            "source": string_series([row.source for row in rows]),
        }
    )


def gaps_frame(runs: Sequence[OutletRun]) -> pd.DataFrame:
    """One row per gap, outlet by outlet in the order searched."""
    import pandas as pd

    gaps = [(run.outlet.id, gap) for run in runs for gap in run.gaps]
    return pd.DataFrame(
        {
            "outlet": string_series([outlet for outlet, _ in gaps]),
            "reason": string_series([gap.reason for _, gap in gaps]),
            "month": string_series(
                [None if gap.month is None else str(gap.month) for _, gap in gaps]
            ),
            "keyword": string_series([gap.keyword for _, gap in gaps]),
            "detail": string_series([gap.detail for _, gap in gaps]),
            "url": string_series([gap.url for _, gap in gaps]),
        }
    )


def string_series(values: Sequence[str | None]) -> pd.Series:
    import pandas as pd

    return pd.Series(values, dtype="string")


def day_series(values: Sequence[date | None]) -> pd.Series:
    """Days as midnight datetimes without a time zone; ``None`` becomes ``NaT``."""
    import pandas as pd

    return pd.to_datetime(pd.Series(list(values), dtype="object")).astype(DAY_DTYPE)


def time_series(values: Sequence[datetime | None]) -> pd.Series:
    """Timezone-aware times in Europe/Istanbul; ``None`` becomes ``NaT``. pandas converts the
    whole list at once, about fifteen times faster than one ``Timestamp`` per value."""
    import pandas as pd

    return pd.Series(list(values), dtype=TIME_DTYPE)


def status_of(run: OutletRun) -> str:
    """``failed`` when nothing could be read, ``incomplete`` when some files or pages failed,
    otherwise ``ok`` (S8)."""
    if run.failure is not None:
        return "failed"
    if any(gap.reason in FAILURE_REASONS for gap in run.gaps):
        return "incomplete"
    return "ok"


def coverage_of(run: OutletRun, keywords: Sequence[str], start: date, end: date) -> str:
    """How much of [start, end) the outlet's archive holds: ``full``, ``partial``, ``none``, or
    ``unknown`` when the outlet failed (S8)."""
    if run.failure is not None:
        return "unknown"
    limits = [gap for gap in run.gaps if gap.reason in COVERAGE_REASONS]
    if not limits:
        return "full"
    if isinstance(run.outlet, SiteSearch):
        searched = {query_text(keyword) for keyword in keywords} - {""}
        stopped = {
            query_text(gap.keyword or "")
            for gap in limits
            if gap.reached is None or gap.reached >= end
        }
        return "none" if searched <= stopped else "partial"
    outside = {gap.month for gap in limits}
    return "none" if set(Month.span(start, end)) <= outside else "partial"


def detail_of(run: OutletRun) -> str:
    """Why the outlet has gaps, in at most three distinct sentences; the failure, if it failed."""
    if run.failure is not None:
        return run.failure
    sentences = list(dict.fromkeys(gap.detail for gap in run.gaps))
    if len(sentences) > MAX_DETAILS:
        sentences = [*sentences[:MAX_DETAILS], f"and {len(sentences) - MAX_DETAILS} more"]
    return "; ".join(sentences)


def http_counts(outlet: Outlet, stats: Mapping[str, HostStats]) -> dict[str, int | bool]:
    """The http layer's counts for every host of ``outlet``, added up. ``errors`` counts
    failed and refused requests."""
    hosts = [stats[host] for host in sorted(outlet.hosts) if host in stats]
    return {
        "requests": sum(host.requests for host in hosts),
        "cache_hits": sum(host.cache_hits for host in hosts),
        "retries": sum(host.retries for host in hosts),
        "errors": sum(host.errors + host.blocked for host in hosts),
        "robots_override": any(host.robots_override for host in hosts),
    }


def report_frame(
    runs: Sequence[OutletRun],
    articles: Mapping[str, int],
    keywords: Sequence[str],
    start: date,
    end: date,
    stats: Mapping[str, HostStats],
) -> pd.DataFrame:
    """One row per outlet, in the order searched. The http counts add up every host of the
    outlet; ``errors`` counts failed and refused requests."""
    import pandas as pd

    records = []
    for run in runs:
        records.append(
            {
                "outlet": run.outlet.id,
                "name": run.outlet.name,
                "method": run.outlet.method,
                "status": status_of(run),
                "coverage": coverage_of(run, keywords, start, end),
                "articles": articles.get(run.outlet.id, 0),
                "candidates": run.candidates,
                "trimmed": run.trimmed,
                "unconfirmed": run.unconfirmed,
                "dates": "day" if isinstance(run.outlet, SiteSearch) else "month",
                "detail": detail_of(run),
                **http_counts(run.outlet, stats),
            }
        )
    columns: dict[str, pd.Series] = {}
    for name in REPORT_COLUMNS:
        values = [record[name] for record in records]
        if name in (*REPORT_COUNTS, *HTTP_COUNTS):
            columns[name] = pd.Series(values, dtype="int64")
        elif name == "robots_override":
            columns[name] = pd.Series(values, dtype="bool")
        else:
            columns[name] = pd.Series(values, dtype="string")
    return pd.DataFrame(columns)


@dataclass(frozen=True, eq=False, repr=False)
class SearchResult:
    """What ``search()`` found: the articles, a report on every outlet, and every gap.

    ``print(result)`` shows a short summary. The other fields record what was searched and
    when, so a dataset built from the result can say where it came from.
    """

    articles: pd.DataFrame
    """One row per article; see the documentation for the columns."""
    report: pd.DataFrame
    """One row per outlet, in the order searched."""
    gaps: pd.DataFrame
    """One row per part of the range that wasn't read, and why."""
    keywords: tuple[str, ...]
    start: date
    end: date
    """The day after the last day searched."""
    outlets: tuple[Outlet, ...]
    searched_at: datetime
    """When the search ran, in Europe/Istanbul."""
    version: str
    """The tr-news-scraper version that ran it."""

    def __repr__(self) -> str:
        return f"SearchResult({self._headline()})"

    def __str__(self) -> str:
        names = [str(name) for name in self.report["name"]]
        counts = [f"{int(count):,}" for count in self.report["articles"]]
        name_width = max(map(len, names), default=0)
        count_width = max(map(len, counts), default=0)
        lines = [self._headline()]
        for name, count, status, detail in zip(
            names, counts, self.report["status"], self.report["detail"], strict=True
        ):
            note = detail if status == "ok" else f"{status}: {detail}"
            lines.append(f"  {name:<{name_width}}  {count:>{count_width}}  {note}".rstrip())
        if bool(self.articles["day"].isna().any()):
            lines.append(DATES_NOTE)
        return "\n".join(lines)

    def _headline(self) -> str:
        last = self.end - timedelta(days=1)
        days = str(self.start) if last == self.start else f"{self.start} to {last}"
        found = len(self.articles)
        searched = len(self.report)
        with_articles = int((self.report["articles"] > 0).sum())
        return (
            f"{', '.join(self.keywords)}, {days}: {found:,} {_plural(found, 'article')} "
            f"from {with_articles} of {searched} {_plural(searched, 'outlet')}"
        )


def build_result(
    runs: Sequence[OutletRun],
    *,
    keywords: Sequence[str],
    start: date,
    end: date,
    outlets: Sequence[Outlet],
    searched_at: datetime,
    version: str,
    stats: Mapping[str, HostStats],
) -> SearchResult:
    """Merge every outlet's rows into one table, and report on each outlet."""
    order = {outlet.id: position for position, outlet in enumerate(outlets)}
    rows = merge((row for run in runs for row in run.rows), keywords, order)
    return SearchResult(
        articles=articles_frame(rows),
        report=report_frame(runs, Counter(row.outlet for row in rows), keywords, start, end, stats),
        gaps=gaps_frame(runs),
        keywords=tuple(keywords),
        start=start,
        end=end,
        outlets=tuple(outlets),
        searched_at=searched_at,
        version=version,
    )


def _plural(count: int, word: str) -> str:
    return word if count == 1 else f"{word}s"
