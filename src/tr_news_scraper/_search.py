"""search(): keywords and a past date range in, one table of matching articles out (internal)."""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from contextlib import suppress
from datetime import date, datetime, time, timedelta

from tr_news_scraper._http import Http
from tr_news_scraper._table import OutletRun, Row, clean_lastmod, clean_title, clean_url
from tr_news_scraper.errors import OutletFailed
from tr_news_scraper.matching import KeywordQuery, tr_lower
from tr_news_scraper.outlets import (
    Candidate,
    Month,
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
    if candidate.lastmod is None:
        return False
    edited = candidate.lastmod.astimezone(ISTANBUL)
    if Month.of(edited.date()) < candidate.month:
        return False
    return edited < datetime.combine(start - timedelta(days=1), time(), ISTANBUL)


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
        elif edited_before(candidate, start):
            run.trimmed += 1
            continue
        found = {match.keyword for match in matches}
        run.rows.append(
            Row(
                outlet=run.outlet.id,
                url=clean_url(candidate.url),
                month=candidate.month,
                matched=tuple(keyword for keyword in query.keywords if keyword in found),
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
