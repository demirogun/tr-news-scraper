"""fetch(): read each article politely, extract it once, and keep what it says (internal)."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime

from tr_news_scraper._extract import Extracted, extract, extractor, from_json, to_json
from tr_news_scraper._http import CachePolicy, Http
from tr_news_scraper.errors import HttpError
from tr_news_scraper.outlets import Outlet
from tr_news_scraper.outlets._scan import describe

logger = logging.getLogger("tr_news_scraper.fetch")

HTML_ACCEPT = "text/html, application/xhtml+xml;q=0.9, */*;q=0.1"
HTML_TYPES = frozenset({"text/html", "application/xhtml+xml"})
PROGRESS_EVERY = 100
OFFLINE_MISS = "it isn't in the cache (offline mode)"

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
                _duration(left),
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


def _duration(seconds: float) -> str:
    if seconds < 90:
        return f"{max(round(seconds), 1)} s"
    if seconds < 90 * 60:
        return f"{round(seconds / 60)} min"
    return f"{seconds / 3600:.1f} h"
