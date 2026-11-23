"""Health checks: is each outlet's archive still where its definition says, and still readable?

The weekly live check and ``coverage(check=True)`` run these. A check reads the archive fresh,
not from the cache, and costs two to four requests.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from itertools import pairwise
from statistics import median_low

from tr_news_scraper._http import Http
from tr_news_scraper.outlets._chunks import Chunk, listed_chunks, read_chunk
from tr_news_scraper.outlets._dates import ISTANBUL
from tr_news_scraper.outlets._model import (
    ChunkedSitemap,
    Month,
    MonthlySitemap,
    Outlet,
    SiteSearch,
)
from tr_news_scraper.outlets._scan import HTML_ACCEPT, READ_ERRORS, XML_ACCEPT, describe
from tr_news_scraper.outlets._search import Page, page_url, parse_page
from tr_news_scraper.outlets._sitemaps import (
    MonthFile,
    article_id,
    listed_months,
    read_month_file,
)

MAX_FILES = 3
"""Monthly sitemaps: the most of last month's files read, in index order, to find entries."""
MIN_ID_PERCENT = 99
"""Monthly sitemaps with ``article_id``: the share of entries whose URL must give one."""
ORDER_BLOCKS = 10
"""Chunked sitemaps: the newest file's dated entries are split into this many blocks, in the
declared order, to judge it."""
MIN_IN_ORDER = 0.9
"""The share of steps between neighbouring blocks whose median dates must follow
``entry_order``. Medians shrug off the articles edited later, which on busy sites put a quarter of
neighbouring entries out of order."""
MIN_SEARCH_RESULTS = 10
MAX_SEARCH_AGE_DAYS = 14


@dataclass(frozen=True, slots=True)
class Health:
    """The result of one outlet's health check."""

    outlet: str
    problems: tuple[str, ...]
    """What's wrong, one sentence each; empty when the outlet is healthy."""
    oldest: Month | None = None
    """Monthly sitemaps: the first month the index lists. Chunked sitemaps: the month of the
    oldest file's first article."""
    newest: Month | None = None
    """Monthly sitemaps: the last month the index lists. Chunked sitemaps: the month of the
    newest file's newest date."""
    sample: int = 0
    """Candidates in the first of last month's files that has entries, in a chunked archive's
    newest file, or kept results on page 1 of the search."""

    @property
    def ok(self) -> bool:
        return not self.problems


def check(outlet: Outlet, http: Http, *, today: date, query: str = "deprem") -> Health:
    """Check that ``outlet``'s archive still works. ``today`` is the date in Europe/Istanbul;
    ``query`` is what a site-search outlet is searched for."""
    if isinstance(outlet, MonthlySitemap):
        return _check_sitemaps(outlet, http, today)
    if isinstance(outlet, ChunkedSitemap):
        return _check_chunks(outlet, http, today)
    return _check_search(outlet, http, today, query)


def _check_sitemaps(outlet: MonthlySitemap, http: Http, today: date) -> Health:
    try:
        index = http.get(outlet.index, allowed_hosts=outlet.hosts, accept=XML_ACCEPT).xml()
        listed = listed_months(index, outlet)
    except READ_ERRORS as error:
        return Health(outlet.id, (f"its sitemap index couldn't be read: {describe(error)}",))
    if not listed:
        return Health(outlet.id, ("no entry in its sitemap index matches month_file",))
    oldest, newest = min(listed), max(listed)
    last_month = Month.of(today).previous()
    problems: list[str] = []
    if newest < last_month:
        problems.append(f"its index ends in {newest}, so the archive seems to have stopped")
    if outlet.earliest is not None and oldest > outlet.earliest:
        problems.append(f"its index now starts in {oldest}, after the declared {outlet.earliest}")
    sample = 0
    files = listed.get(last_month, ())
    if not files:
        problems.append(f"its index doesn't list last month ({last_month})")
        return Health(outlet.id, tuple(problems), oldest, newest, sample)
    urls = iter(files[:MAX_FILES])
    try:
        found = _read_file(outlet, http, last_month, next(urls))
        read = 1
        while not found.entries and (url := next(urls, None)) is not None:
            found = _read_file(outlet, http, last_month, url)
            read += 1
    except READ_ERRORS as error:
        problems.append(f"the file for {last_month} couldn't be read: {describe(error)}")
        return Health(outlet.id, tuple(problems), oldest, newest, sample)
    sample = len(found.candidates)
    if found.entries == 0:
        files_read = "the file" if read == 1 else f"the first {read} files"
        problems.append(f"{files_read} for {last_month} {'is' if read == 1 else 'are'} empty")
    elif found.dropped * 100 > found.entries:
        problems.append(
            f"{found.dropped} of {found.entries} entries in the file for {last_month} "
            "aren't HTTPS URLs on its hosts"
        )
    titled = sum(1 for candidate in found.candidates if candidate.title)
    if outlet.titles is not None and titled * 2 < len(found.candidates):
        problems.append(
            f"only {titled} of {len(found.candidates)} entries in the file for "
            f"{last_month} have a headline"
        )
    if outlet.id_pattern is not None:
        with_id = sum(1 for c in found.candidates if article_id(outlet, c.url) is not None)
        if with_id * 100 < MIN_ID_PERCENT * len(found.candidates):
            problems.append(
                f"only {with_id} of {len(found.candidates)} entries in the file for "
                f"{last_month} give an article id"
            )
    return Health(outlet.id, tuple(problems), oldest, newest, sample)


def _read_file(outlet: MonthlySitemap, http: Http, month: Month, url: str) -> MonthFile:
    response = http.get(url, allowed_hosts=outlet.hosts, accept=XML_ACCEPT)
    return read_month_file(response.xml(), outlet, month, url)


def _check_chunks(outlet: ChunkedSitemap, http: Http, today: date) -> Health:
    """Three requests: the index, the newest file and the oldest file (K7)."""
    try:
        index = http.get(outlet.index, allowed_hosts=outlet.hosts, accept=XML_ACCEPT).xml()
        urls = listed_chunks(index, outlet)
    except READ_ERRORS as error:
        return Health(outlet.id, (f"its sitemap index couldn't be read: {describe(error)}",))
    if not urls:
        return Health(outlet.id, ("no entry in its sitemap index matches chunk_file",))
    try:
        newest = _chunk(outlet, http, urls[-1], today)
    except READ_ERRORS as error:
        return Health(outlet.id, (f"its newest file couldn't be read: {describe(error)}",))
    problems = [*_chunk_problems(outlet, newest, today)]
    oldest_month = None
    try:
        oldest = newest if len(urls) == 1 else _chunk(outlet, http, urls[0], today)
    except READ_ERRORS as error:
        problems.append(f"its oldest file couldn't be read: {describe(error)}")
    else:
        if oldest.oldest is not None:
            oldest_month = Month.of(oldest.oldest.astimezone(ISTANBUL).date())
            if outlet.earliest is not None and oldest_month > outlet.earliest.next():
                problems.append(
                    f"its oldest file is dated {oldest_month}, more than a month after the "
                    f"declared {outlet.earliest}"
                )
    newest_month = (
        None if newest.newest is None else Month.of(newest.newest.astimezone(ISTANBUL).date())
    )
    return Health(outlet.id, tuple(problems), oldest_month, newest_month, len(newest.entries))


def _chunk(outlet: ChunkedSitemap, http: Http, url: str, today: date) -> Chunk:
    response = http.get(url, allowed_hosts=outlet.hosts, accept=XML_ACCEPT)
    return read_chunk(response.xml(), outlet, url, today=today)


def _chunk_problems(outlet: ChunkedSitemap, newest: Chunk, today: date) -> list[str]:
    """What's wrong with the newest file of a chunked archive (K7)."""
    if newest.total == 0:
        return ["its newest file is empty"]
    problems = []
    if newest.dropped * 100 > newest.total:
        problems.append(
            f"{newest.dropped} of {newest.total} entries in its newest file "
            "aren't HTTPS URLs on its hosts"
        )
    if newest.newest is None:
        problems.append("its newest file has no dates")
    elif (today - newest.newest.astimezone(ISTANBUL).date()).days > MAX_SEARCH_AGE_DAYS:
        problems.append(
            f"its newest file's newest date is {newest.newest.astimezone(ISTANBUL).date()}, "
            f"more than {MAX_SEARCH_AGE_DAYS} days ago"
        )
    dated = [found for found in newest.dates if found is not None]
    if len(dated) >= 2 * ORDER_BLOCKS:
        size = len(dated) // ORDER_BLOCKS
        medians = [median_low(dated[i * size : (i + 1) * size]) for i in range(ORDER_BLOCKS)]
        steps = ORDER_BLOCKS - 1
        in_order = sum(1 for earlier, later in pairwise(medians) if earlier <= later)
        if in_order < MIN_IN_ORDER * steps:
            problems.append(
                f"its newest file's dates don't follow entry_order ({outlet.entry_order}): only "
                f"{in_order} of {steps} steps between blocks of its entries do"
            )
    titled = sum(1 for entry in newest.entries if entry.title)
    if outlet.titles is not None and titled * 2 < len(newest.entries):
        problems.append(
            f"only {titled} of {len(newest.entries)} entries in its newest file have a headline"
        )
    return problems


def _check_search(outlet: SiteSearch, http: Http, today: date, query: str) -> Health:
    pages: list[Page] = []
    for number in (1, 2):
        url = page_url(outlet, query, number)
        try:
            text = http.get(url, allowed_hosts=outlet.hosts, accept=HTML_ACCEPT).text()
            pages.append(parse_page(text, outlet, number, url))
        except READ_ERRORS as error:
            return Health(outlet.id, (f"page {number} couldn't be read: {describe(error)}",))
    first, second = pages
    problems: list[str] = []
    complete = [r for r in first.results if r.title or "title" not in outlet.xpaths]
    if len(complete) < MIN_SEARCH_RESULTS:
        problems.append(
            f"page 1 for {query!r} has {len(complete)} complete results; "
            f"at least {MIN_SEARCH_RESULTS} were expected"
        )
    for page in pages:
        if list(page.days) != sorted(page.days, reverse=True):
            problems.append(f"the dates on page {page.number} aren't newest first")
    if not first.empty and not second.empty and second.newest > first.oldest:
        problems.append("page 2 has results newer than page 1's")
    if not first.empty and (today - first.newest).days > MAX_SEARCH_AGE_DAYS:
        problems.append(
            f"its newest result is from {first.newest}, more than {MAX_SEARCH_AGE_DAYS} days ago"
        )
    return Health(outlet.id, tuple(problems), sample=len(first.results))
