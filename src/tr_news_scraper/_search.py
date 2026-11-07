"""search(): keywords and a past date range in, one table of matching articles out (internal)."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import FIRST_EXCEPTION, Future, ThreadPoolExecutor, wait
from contextlib import suppress
from datetime import date, datetime, time, timedelta
from pathlib import Path

from tr_news_scraper._http import Http, HttpConfig
from tr_news_scraper._table import (
    OutletRun,
    Row,
    SearchResult,
    build_result,
    clean_lastmod,
    clean_title,
    clean_url,
)
from tr_news_scraper._version import __version__
from tr_news_scraper.errors import OutletFailed, SearchFailed
from tr_news_scraper.matching import KeywordQuery, tr_lower
from tr_news_scraper.outlets import (
    Candidate,
    MonthlySitemap,
    Outlet,
    SiteSearch,
    builtin,
    get,
)
from tr_news_scraper.outlets._dates import ISTANBUL
from tr_news_scraper.outlets._scan import scan

logger = logging.getLogger("tr_news_scraper.search")

_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
_OUTLET_KINDS = (MonthlySitemap, SiteSearch)
_WAIT_STEP = 0.1
"""Seconds the main thread waits on the workers at a time: on Windows, Ctrl+C reaches a waiting
thread only when its wait returns."""
_OFFLINE_HINT = (
    "Nothing for this search is in the cache yet: search once without offline=True to fill it."
)


def parse_keywords(keywords: str | Iterable[str]) -> tuple[str, ...]:
    """The keywords to search for (S1). A ``str`` is one keyword. Blank and repeated keywords
    are dropped; a repeat differs only in case and keeps the first spelling."""
    items: Iterable[object] = [keywords] if isinstance(keywords, str) else keywords
    kept: dict[str, str] = {}
    for item in items:
        if not isinstance(item, str):
            raise TypeError(f"keywords must be strings, not {type(item).__name__}")
        text = item.strip()
        if text:
            kept.setdefault(tr_lower(text), text)
    if not kept:
        raise ValueError("give at least one keyword, such as 'deprem'")
    return tuple(kept.values())


def parse_day(value: object, name: str) -> date:
    """A day in Türkiye, given as a ``date`` or ``"YYYY-MM-DD"`` (S1)."""
    if isinstance(value, datetime):
        raise TypeError(f"{name} must be a date, not a datetime: a range is whole days in Türkiye")
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a date or 'YYYY-MM-DD', not {type(value).__name__}")
    text = value.strip()
    if _DAY.fullmatch(text):
        with suppress(ValueError):
            return date.fromisoformat(text)
    raise ValueError(f"{name} must be a date or 'YYYY-MM-DD', such as '2023-02-01', not {value!r}")


def parse_range(start: date | str, end: date | str) -> tuple[date, date]:
    """The range [start, end): whole days in Türkiye, the end excluded (S1)."""
    first, after = parse_day(start, "start"), parse_day(end, "end")
    if first >= after:
        raise ValueError(
            f"the start ({first}) must be before the end ({after}); "
            "the end is the day after the last day you want"
        )
    return first, after


def resolve_outlets(
    outlets: str | Outlet | Iterable[str | Outlet] | None,
) -> tuple[Outlet, ...]:
    """The outlets to search, in the order given; every built-in outlet by default (S1)."""
    if outlets is None:
        return builtin()
    items: Iterable[object] = [outlets] if isinstance(outlets, (str, *_OUTLET_KINDS)) else outlets
    chosen: dict[str, Outlet] = {}
    for item in items:
        outlet = get(item) if isinstance(item, str) else item
        if not isinstance(outlet, _OUTLET_KINDS):
            raise TypeError(f"outlets must be outlet ids or definitions, not {type(item).__name__}")
        if outlet.id in chosen:
            raise ValueError(f"two outlets share the id {outlet.id!r}")
        chosen[outlet.id] = outlet
    if not chosen:
        raise ValueError("choose at least one outlet, or leave outlets out to search them all")
    return tuple(chosen.values())


def edited_before(candidate: Candidate, start: date) -> bool:
    """Whether a sitemap entry was last edited more than a day before ``start`` (S4).

    A page can't be edited before it's published, so such an entry is outside the range. The
    extra day absorbs sites that write UTC times without an offset. A last edit before the
    entry's own month contradicts the archive, so it can't rule the entry out.
    """
    return _edited_before(candidate, _cutoff(start))


def _cutoff(start: date) -> datetime:
    """Midnight in Türkiye a day before ``start``: an entry last edited earlier is out."""
    return datetime.combine(start - timedelta(days=1), time(), ISTANBUL)


def _edited_before(candidate: Candidate, cutoff: datetime) -> bool:
    if candidate.lastmod is None:
        return False
    edited = candidate.lastmod.astimezone(ISTANBUL)
    month = candidate.month
    if (edited.year, edited.month) < (month.year, month.month):
        return False
    return edited < cutoff


def collect(
    run: OutletRun,
    candidates: Iterable[Candidate],
    query: KeywordQuery,
    start: date,
    end: date,
) -> None:
    """Keep the candidates that name a keyword and can lie in [start, end) (S3, S4).

    Every candidate counts in ``run.candidates``. A search result that names no keyword counts
    as unconfirmed, and a matching entry ruled out by its dates counts as trimmed.
    """
    searched = isinstance(run.outlet, SiteSearch)
    keywords = query.keywords
    cutoff = _cutoff(start)
    for candidate in candidates:
        run.candidates += 1
        title = clean_title(candidate.title)
        matches = query.match(title=title, url=candidate.url)
        if not matches:
            run.unconfirmed += searched
            continue
        if candidate.day is not None:
            if not start <= candidate.day < end:
                run.trimmed += 1
                continue
        elif _edited_before(candidate, cutoff):
            run.trimmed += 1
            continue
        found = {match.keyword for match in matches}
        run.rows.append(
            Row(
                outlet=run.outlet.id,
                url=clean_url(candidate.url),
                month=candidate.month,
                matched=tuple(keyword for keyword in keywords if keyword in found),
                reasons=tuple(match.reason for match in matches),
                source=candidate.source,
                title=title,
                day=candidate.day,
                lastmod=clean_lastmod(candidate.lastmod),
            )
        )


def run_outlet(
    outlet: Outlet,
    http: Http,
    query: KeywordQuery,
    start: date,
    end: date,
    *,
    today: date,
    offline: bool,
) -> OutletRun:
    """Scan one outlet's archive and keep its matching candidates.

    ``OutletFailed`` becomes the run's ``failure``. Any other exception, including a cancelled
    request, ends the run and propagates.
    """
    run = OutletRun(outlet)
    found = scan(outlet, http, start, end, query.keywords, today=today, offline=offline)
    try:
        collect(run, found, query, start, end)
    except OutletFailed as failure:
        run.failure = failure.reason
        logger.warning("%s failed: %s", outlet.name, failure.reason)
    run.gaps = list(found.gaps)
    if run.failure is None:
        logger.info(
            "%s: %d matching articles among %d candidates, %d gap(s)",
            outlet.name,
            len(run.rows),
            run.candidates,
            len(run.gaps),
        )
    return run


def search(
    keywords: str | Iterable[str],
    start: date | str,
    end: date | str,
    *,
    outlets: str | Outlet | Iterable[str | Outlet] | None = None,
    contact: str | None = None,
    obey_robots: bool = True,
    offline: bool = False,
    cache_dir: str | Path | None = None,
) -> SearchResult:
    """Find news articles whose headline or URL names any of ``keywords``, published from
    ``start`` up to the day before ``end``.

    >>> result = search(["deprem", "tsunami"], "2023-02-01", "2023-03-01")
    >>> result.articles   # one row per article: outlet, month, day, title, url, matched, ...
    >>> print(result)     # what each outlet found, and why some found nothing

    Every outlet's archive is read at the same time, one request per second per site, through
    one client that obeys robots.txt and names itself honestly. Days are in Türkiye; a ``str``
    keyword or outlet counts as one.

    Args:
        keywords: Words or phrases; any of them may match. ``word*`` forces prefix matching and
            ``"word"`` an exact match.
        start: The first day, as a ``date`` or ``"YYYY-MM-DD"``.
        end: The day after the last day.
        outlets: Built-in outlet ids or outlet definitions; every built-in outlet by default.
        contact: Added to the User-Agent, such as ``"mailto:you@example.org"``.
        obey_robots: ``False`` skips the robots.txt check, with a warning for every site. Only
            use it when you have the site's permission.
        offline: Answer only from the cache of earlier searches.
        cache_dir: Where responses are cached; the user cache folder by default.

    Raises:
        ValueError: An input is invalid; nothing was requested.
        SearchFailed: Every outlet failed.
    """
    config = HttpConfig(
        contact=contact,
        obey_robots=obey_robots,
        cache_dir=None if cache_dir is None else Path(cache_dir),
    )
    with Http(config) as http:
        return _search(
            keywords,
            start,
            end,
            outlets=outlets,
            http=http,
            now=datetime.now(ISTANBUL),
            offline=offline,
        )


def _search(
    keywords: str | Iterable[str],
    start: date | str,
    end: date | str,
    *,
    outlets: str | Outlet | Iterable[str | Outlet] | None,
    http: Http,
    now: datetime,
    offline: bool,
) -> SearchResult:
    """``search()`` with the client and the current time (Europe/Istanbul) given, for tests."""
    query = KeywordQuery(parse_keywords(keywords))
    first, after = parse_range(start, end)
    chosen = resolve_outlets(outlets)
    today = now.date()
    runs = in_threads(
        chosen,
        http,
        lambda outlet: run_outlet(outlet, http, query, first, after, today=today, offline=offline),
    )
    failures = {run.outlet.id: run.failure for run in runs if run.failure is not None}
    if len(failures) == len(runs):
        raise SearchFailed(failures, hint=_OFFLINE_HINT if offline else None)
    return build_result(
        runs,
        keywords=query.keywords,
        start=first,
        end=after,
        outlets=chosen,
        searched_at=now,
        version=__version__,
        stats=http.stats(),
    )


def in_threads[T](outlets: Sequence[Outlet], http: Http, task: Callable[[Outlet], T]) -> list[T]:
    """Run ``task`` for every outlet at once, one thread each, and return the results in order.

    On Ctrl+C, or when a task raises, the client is cancelled: every task stops before its next
    request, and the exception is raised once they have (S2).
    """
    with ThreadPoolExecutor(max_workers=len(outlets), thread_name_prefix="tr-news-scraper") as pool:
        futures = [pool.submit(task, outlet) for outlet in outlets]
        try:
            _wait_for(futures)
        except BaseException:
            http.cancel()
            wait(futures)
            raise
    return [future.result() for future in futures]


def _wait_for[T](futures: Sequence[Future[T]]) -> None:
    """Wait in short steps, so Ctrl+C gets through, and raise the first worker's exception."""
    pending = set(futures)
    while pending:
        done, pending = wait(pending, timeout=_WAIT_STEP, return_when=FIRST_EXCEPTION)
        for future in done:
            future.result()
