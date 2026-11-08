"""fetch(): read each article politely, extract it once, and keep what it says (internal)."""

from __future__ import annotations

import logging
import time
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from tr_news_scraper._extract import Extracted, extract, extractor, from_json, to_json
from tr_news_scraper._http import CachePolicy, Http, HttpConfig
from tr_news_scraper._search import in_threads, parse_keywords, parse_range, resolve_outlets
from tr_news_scraper._table import DAY_DTYPE, SearchResult
from tr_news_scraper._version import __version__
from tr_news_scraper.errors import FetchFailed, HttpError
from tr_news_scraper.matching import KeywordQuery
from tr_news_scraper.outlets import Outlet
from tr_news_scraper.outlets._dates import ISTANBUL
from tr_news_scraper.outlets._scan import describe

if TYPE_CHECKING:
    import pandas as pd

    from tr_news_scraper._fetched import FetchResult

logger = logging.getLogger("tr_news_scraper.fetch")

HTML_ACCEPT = "text/html, application/xhtml+xml;q=0.9, */*;q=0.1"
HTML_TYPES = frozenset({"text/html", "application/xhtml+xml"})
PROGRESS_EVERY = 100
OFFLINE_MISS = "it isn't in the cache (offline mode)"
NOT_READ = "it wasn't read"
_OFFLINE_HINT = (
    "Nothing for these articles is in the cache yet: fetch once without offline=True to fill it."
)

Progress = Callable[[str, int, int], None]
"""Called after every article with the outlet's id, the articles done, and its total."""


@dataclass(frozen=True, slots=True)
class Fetched:
    """One article's result: what its page says, or why it couldn't be read."""

    extracted: Extracted
    fetched_at: datetime | None = None
    """When the page was downloaded; a kept record keeps its first time."""
    cached: bool = False


@dataclass(slots=True)
class FetchRun:
    """One outlet's results, by row position."""

    outlet: Outlet
    results: dict[int, Fetched] = field(default_factory=dict)
    downloaded: int = 0
    cached: int = 0
    failed: int = 0


def fetch_outlet(
    outlet: Outlet,
    rows: Sequence[tuple[int, str]],
    http: Http,
    *,
    refresh: bool,
    offline: bool,
    progress: Progress | None,
    clock: Callable[[], float] = time.monotonic,
) -> FetchRun:
    """Read ``rows`` (row position, URL) one after another (F2), reporting progress (F9)."""
    run = FetchRun(outlet)
    version = extractor()
    started = clock()
    for done, (position, url) in enumerate(rows, start=1):
        result = _read(outlet, url, http, version, refresh=refresh, offline=offline)
        run.results[position] = result
        if result.extracted.error is not None:
            run.failed += 1
        elif result.cached:
            run.cached += 1
        else:
            run.downloaded += 1
        if progress is not None:
            progress(outlet.id, done, len(rows))
        if done % PROGRESS_EVERY == 0 and done < len(rows):
            left = (clock() - started) / done * (len(rows) - done)
            logger.info(
                "%s: %d of %d articles read, about %s left",
                outlet.name,
                done,
                len(rows),
                duration(left),
                extra={"progress": True},
            )
    logger.info(
        "%s: %d articles read: %d downloaded, %d from the cache, %d failed",
        outlet.name,
        len(rows),
        run.downloaded,
        run.cached,
        run.failed,
    )
    return run


def _read(
    outlet: Outlet, url: str, http: Http, version: str, *, refresh: bool, offline: bool
) -> Fetched:
    """One article: its kept record, or its page downloaded and extracted (F8).

    Pages are never stored; only a successful extraction is kept, so a failure is tried again
    on the next run.
    """
    name = f"{version}\n{url}"
    if not refresh:
        data = http.load_record(name)
        if data is not None:
            try:
                extracted, fetched_at = from_json(data)
            except (ValueError, KeyError, TypeError):
                logger.debug("the record for %s is damaged; reading the page again", url)
            else:
                return Fetched(extracted, fetched_at, cached=True)
    if offline:
        return Fetched(Extracted(error=OFFLINE_MISS))
    try:
        page = http.get(
            url, allowed_hosts=outlet.hosts, accept=HTML_ACCEPT, cache=CachePolicy(no_store=True)
        )
    except HttpError as error:
        return Fetched(Extracted(error=describe(error)))
    kind = page.headers.get("content-type", "").partition(";")[0].strip().lower()
    if kind and kind not in HTML_TYPES:
        return Fetched(Extracted(error=f"it isn't a web page ({kind})"), page.fetched_at)
    extracted = extract(page.text(), page.url)
    if extracted.error is None:
        http.store_record(name, to_json(extracted, page.fetched_at))
    return Fetched(extracted, page.fetched_at)


def duration(seconds: float) -> str:
    """A time left, roughly: "45 s", "10 min" or "2.5 h"."""
    if seconds < 90:
        return f"{max(round(seconds), 1)} s"
    if seconds < 90 * 60:
        return f"{round(seconds / 60)} min"
    return f"{seconds / 3600:.1f} h"


def fetch(
    articles: SearchResult | pd.DataFrame,
    *,
    keywords: str | Iterable[str] | None = None,
    start: date | str | None = None,
    end: date | str | None = None,
    outlets: str | Outlet | Iterable[str | Outlet] | None = None,
    progress: Progress | None = None,
    contact: str | None = None,
    obey_robots: bool = True,
    offline: bool = False,
    refresh: bool = False,
    cache_dir: str | Path | None = None,
) -> FetchResult:
    """Download every article and read its text, author and publication time.

    >>> found = search(["deprem"], "2023-02-01", "2023-03-01")
    >>> fetched = fetch(found)        # or fetch(found.articles.head(100))
    >>> fetched.articles              # search's columns plus text, author, published, ...
    >>> print(fetched)                # what each outlet read, and what failed

    Each outlet's pages are read one at a time, a second apart, through the same polite client
    as ``search()``, and the outlets run at the same time. Only what each page says is kept, in
    the cache folder, so running the same call again continues where it stopped.

    Args:
        articles: A SearchResult, or a DataFrame with ``outlet`` and ``url`` columns, such as a
            filtered ``result.articles``.
        keywords: The keywords to look for in a DataFrame's texts (``text_matched``). A
            SearchResult brings its own.
        start: A DataFrame's first day. With ``end``, rows whose page dates them outside the
            range move to ``outside``. A SearchResult brings its own range.
        end: The day after a DataFrame's last day.
        outlets: The definitions of custom outlets that a DataFrame's rows name.
        progress: Called after every article with the outlet's id, the articles done, and the
            outlet's total.
        contact: As in ``search()``.
        obey_robots: As in ``search()``.
        offline: Read only articles already in the cache.
        refresh: Download every article again, even when it's in the cache.
        cache_dir: As in ``search()``.

    Raises:
        ValueError: An input is invalid; nothing was requested.
        FetchFailed: No article could be read.
    """
    config = HttpConfig(
        contact=contact,
        obey_robots=obey_robots,
        cache_dir=None if cache_dir is None else Path(cache_dir),
    )
    with Http(config) as http:
        return _fetch(
            articles,
            keywords=keywords,
            start=start,
            end=end,
            outlets=outlets,
            progress=progress,
            http=http,
            now=datetime.now(ISTANBUL),
            offline=offline,
            refresh=refresh,
        )


def _fetch(
    articles: SearchResult | pd.DataFrame,
    *,
    start: date | str | None,
    end: date | str | None,
    outlets: str | Outlet | Iterable[str | Outlet] | None,
    progress: Progress | None,
    http: Http,
    now: datetime,
    offline: bool,
    refresh: bool,
    keywords: str | Iterable[str] | None = None,
) -> FetchResult:
    """``fetch()`` with the client and the current time (Europe/Istanbul) given, for tests."""
    from tr_news_scraper._fetched import build_fetch_result

    table, keywords, first, after, chosen = _inputs(articles, keywords, start, end, outlets)
    rows: dict[str, list[tuple[int, str]]] = {}
    for position, (outlet, url) in enumerate(zip(table["outlet"], table["url"], strict=True)):
        rows.setdefault(str(outlet), []).append((position, str(url)))
    active = [outlet for outlet in chosen if outlet.id in rows]
    runs = (
        in_threads(
            active,
            http,
            lambda outlet: fetch_outlet(
                outlet, rows[outlet.id], http, refresh=refresh, offline=offline, progress=progress
            ),
        )
        if active
        else []
    )
    read = any(r.extracted.error is None for run in runs for r in run.results.values())
    if len(table) and not read:
        failures = {run.outlet.id: _commonest_error(run) for run in runs}
        raise FetchFailed(failures, hint=_OFFLINE_HINT if offline else None)
    return build_fetch_result(
        table,
        runs,
        keywords=keywords,
        start=first,
        end=after,
        outlets=chosen,
        fetched_at=now,
        version=__version__,
        stats=http.stats(),
    )


def _inputs(
    articles: Any,
    keywords: str | Iterable[str] | None,
    start: date | str | None,
    end: date | str | None,
    outlets: str | Outlet | Iterable[str | Outlet] | None,
) -> tuple[pd.DataFrame, tuple[str, ...], date | None, date | None, tuple[Outlet, ...]]:
    """The table, keywords, range and outlets to fetch with, checked before any request (F1)."""
    import pandas as pd

    if isinstance(articles, SearchResult):
        if any(value is not None for value in (keywords, start, end, outlets)):
            raise ValueError(
                "a SearchResult brings its own keywords, range and outlets; to choose others, "
                "fetch its articles table instead"
            )
        return articles.articles, articles.keywords, articles.start, articles.end, articles.outlets
    if not isinstance(articles, pd.DataFrame):
        raise TypeError(f"fetch takes a SearchResult or a DataFrame, not {type(articles).__name__}")
    if "outlet" not in articles.columns or "url" not in articles.columns:
        found = ", ".join(map(str, articles.columns)) or "none"
        raise ValueError(f"the table needs the columns outlet and url; it has: {found}")
    missing = (articles["outlet"].isna() | articles["url"].isna()).tolist()
    if any(missing):
        raise ValueError(f"row {missing.index(True)} has no outlet or no url")
    if (start is None) != (end is None):
        raise ValueError("give both start and end, or neither")
    first, after = (None, None) if start is None or end is None else parse_range(start, end)
    chosen = resolve_outlets(outlets)
    unknown = sorted({str(outlet) for outlet in articles["outlet"]} - {o.id for o in chosen})
    if unknown:
        raise ValueError(f"no outlet definition for {', '.join(unknown)}; pass it in outlets")
    words = () if keywords is None else KeywordQuery(parse_keywords(keywords)).keywords
    return _typed(articles), words, first, after, chosen


def _typed(articles: pd.DataFrame) -> pd.DataFrame:
    """A table whose ``day`` holds dates and whose ``title`` holds strings, as in search's, so
    tables read from files or built by hand work the same (F1)."""
    import pandas as pd

    if "day" not in articles.columns and "title" not in articles.columns:
        return articles
    table = articles.copy()
    if "day" in table.columns:
        try:
            days = pd.to_datetime(table["day"])
        except (ValueError, TypeError) as error:
            raise ValueError("the day column must hold dates, such as 2023-02-12") from error
        if days.dt.tz is not None:
            days = days.dt.tz_convert(ISTANBUL).dt.tz_localize(None)
        table["day"] = days.dt.normalize().astype(DAY_DTYPE)
    if "title" in table.columns:
        table["title"] = table["title"].astype("string")
    return table


def _commonest_error(run: FetchRun) -> str:
    errors = Counter(r.extracted.error for r in run.results.values() if r.extracted.error)
    return errors.most_common(1)[0][0] if errors else NOT_READ
