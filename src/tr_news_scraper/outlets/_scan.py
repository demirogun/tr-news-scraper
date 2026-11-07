"""Scanning one outlet's archive for a date range: the network side of the outlets module.

Search calls :func:`scan` once per outlet and iterates the result in its own thread. Every
request goes through the shared :class:`~tr_news_scraper._http.Http`, which obeys robots.txt,
paces requests per host and caches responses.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable, Iterator, Sequence
from datetime import date, timedelta

from lxml import etree

from tr_news_scraper._http import CachePolicy, Http, Response
from tr_news_scraper.errors import (
    Blocked,
    HostNotAllowed,
    HttpError,
    NotCached,
    OutletFailed,
    RequestFailed,
    ResponseTooLarge,
    RobotsDisallowed,
)
from tr_news_scraper.outlets._model import (
    BOUNDARY_REASONS,
    Candidate,
    Gap,
    GapReason,
    Month,
    MonthlySitemap,
    Outlet,
    SiteSearch,
)
from tr_news_scraper.outlets._search import (
    Outcome,
    Page,
    SearchPageError,
    page_url,
    parse_page,
    query_text,
    results_in_range,
)
from tr_news_scraper.outlets._sitemaps import (
    SitemapError,
    listed_months,
    plan_months,
    read_month_file,
)

logger = logging.getLogger("tr_news_scraper.outlets")

XML_ACCEPT = "application/xml, text/xml;q=0.9, */*;q=0.1"
HTML_ACCEPT = "text/html, */*;q=0.1"
INDEX_TTL = timedelta(hours=1)
SEARCH_TTL = timedelta(hours=1)
READ_ERRORS = (HttpError, etree.LxmlError, SitemapError, SearchPageError)


def month_ttl(month: Month, today: date) -> timedelta:
    """How long a month's file may be served from the cache.

    The current month still gains articles and the previous one gets late edits; older months
    rarely change.
    """
    current = Month.of(today)
    if month >= current:
        return timedelta(hours=1)
    if month == current.previous():
        return timedelta(days=1)
    return timedelta(days=30)


def scan(
    outlet: Outlet,
    http: Http,
    start: date,
    end: date,
    keywords: Sequence[str] = (),
    *,
    today: date,
    offline: bool = False,
) -> Scan:
    """Prepare a scan of ``outlet`` for ``[start, end)``; no request is made until iteration.

    ``keywords`` are used only by site-search outlets. ``today`` (in Europe/Istanbul) decides
    how long cached files stay fresh. With ``offline=True``, only the cache is read.
    """
    return Scan(outlet, http, start, end, keywords, today=today, offline=offline)


class Scan:
    """One outlet's candidates for a date range. Iterate it once; the requests happen then.

    Whatever wasn't read is recorded in :attr:`gaps`, which is complete once iteration ends.
    Iteration raises :class:`~tr_news_scraper.errors.OutletFailed` when nothing could be read.
    """

    def __init__(
        self,
        outlet: Outlet,
        http: Http,
        start: date,
        end: date,
        keywords: Sequence[str],
        *,
        today: date,
        offline: bool,
    ) -> None:
        if start >= end:
            raise ValueError(f"the start ({start}) must be before the end ({end})")
        self.outlet = outlet
        self.gaps: list[Gap] = []
        """What wasn't read, and why."""
        self.months: list[Month] = []
        """The archive months read in full (monthly sitemaps)."""
        self.dropped = 0
        """Entries skipped for not being HTTPS URLs on the outlet's hosts."""
        self._http = http
        self._start = start
        self._end = end
        self._keywords = tuple(keywords)
        self._today = today
        self._offline = offline
        self._started = False
        self._attempts = 0
        self._successes = 0

    def __iter__(self) -> Iterator[Candidate]:
        if self._started:
            raise RuntimeError("a Scan can be iterated only once")
        self._started = True
        return self._run()

    def _run(self) -> Iterator[Candidate]:
        try:
            if isinstance(self.outlet, MonthlySitemap):
                yield from self._monthly(self.outlet)
            else:
                yield from self._site_search(self.outlet)
            if self._attempts and not self._successes:
                raise OutletFailed(self.outlet.id, "none of the files it needed could be read")
        finally:
            self._log_summary()

    def _monthly(self, outlet: MonthlySitemap) -> Iterator[Candidate]:
        try:
            listed = listed_months(self._get(outlet.index, INDEX_TTL, XML_ACCEPT).xml(), outlet)
        except READ_ERRORS as error:
            raise OutletFailed(
                outlet.id, f"its sitemap index couldn't be read: {describe(error)}"
            ) from error
        if not listed:
            raise OutletFailed(outlet.id, "its sitemap index lists no monthly files")
        for step in plan_months(listed, self._start, self._end):
            if isinstance(step, Gap):
                self.gaps.append(step)
                continue
            self._attempts += 1
            try:
                response = self._get(step.url, month_ttl(step.month, self._today), XML_ACCEPT)
                found = read_month_file(response.xml(), outlet, step.month, step.url)
            except READ_ERRORS as error:
                self._fail(error, f"the file for {step.month}", month=step.month, url=step.url)
                continue
            self._successes += 1
            self.months.append(step.month)
            self.dropped += found.dropped
            logger.debug(
                "%s: %s has %d entries, kept %d, dropped %d",
                outlet.name,
                step.url,
                found.entries,
                len(found.candidates),
                found.dropped,
            )
            yield from found.candidates

    def _site_search(self, outlet: SiteSearch) -> Iterator[Candidate]:
        queries: dict[str, str] = {}
        for keyword in self._keywords:
            queries.setdefault(query_text(keyword), keyword)
        for query, keyword in queries.items():
            if not query:
                continue
            outcome = Outcome()
            fetch = self._page_fetcher(outlet, query)
            try:
                for result in results_in_range(
                    fetch, self._start, self._end, outlet.max_pages, outcome
                ):
                    yield Candidate(
                        outlet=outlet.id,
                        url=result.url,
                        month=Month.of(result.day),
                        title=result.title,
                        day=result.day,
                        source=result.source,
                    )
            except READ_ERRORS as error:
                self._fail(
                    error,
                    f"the search for {keyword!r}",
                    keyword=keyword,
                    url=getattr(error, "url", None),
                )
                continue
            if outcome.exhausted:
                gap = Gap(
                    "window",
                    f"{outlet.name}'s search has nothing older than {outcome.oldest_seen} for "
                    f"{keyword!r}, so the rest of the range can't be reached through it",
                    keyword=keyword,
                    reached=outcome.oldest_seen,
                )
                self.gaps.append(gap)
                logger.warning("%s: %s", outlet.name, gap.detail)

    def _page_fetcher(self, outlet: SiteSearch, query: str) -> Callable[[int], Page]:
        def fetch(number: int) -> Page:
            url = page_url(outlet, query, number)
            self._attempts += 1
            page = parse_page(self._get(url, SEARCH_TTL, HTML_ACCEPT).text(), outlet, number, url)
            self._successes += 1
            self.dropped += page.dropped
            logger.debug(
                "%s: page %d has %d results, kept %d, dropped %d, unreadable %d",
                outlet.name,
                number,
                page.items,
                len(page.results),
                page.dropped,
                page.unreadable,
            )
            return page

        return fetch

    def _get(self, url: str, ttl: timedelta, accept: str) -> Response:
        policy = CachePolicy(offline=True) if self._offline else CachePolicy(ttl=ttl)
        return self._http.get(url, allowed_hosts=self.outlet.hosts, accept=accept, cache=policy)

    def _fail(
        self,
        error: Exception,
        what: str,
        *,
        month: Month | None = None,
        keyword: str | None = None,
        url: str | None = None,
    ) -> None:
        reason: GapReason = "failed"
        if isinstance(error, RobotsDisallowed):
            reason = "robots"
        elif isinstance(error, Blocked):
            reason = "blocked"
        gap = Gap(
            reason,
            f"{what} couldn't be read: {describe(error)}",
            month=month,
            keyword=keyword,
            url=url,
        )
        self.gaps.append(gap)
        logger.warning("%s: %s (%s)", self.outlet.name, gap.detail, url)

    def _log_summary(self) -> None:
        boundaries: defaultdict[GapReason, list[Month]] = defaultdict(list)
        for gap in self.gaps:
            if gap.reason in BOUNDARY_REASONS and gap.month is not None:
                boundaries[gap.reason].append(gap.month)
        for reason, months in boundaries.items():
            logger.info(
                "%s: %d month(s) not read (%s), %s to %s",
                self.outlet.name,
                len(months),
                reason,
                min(months),
                max(months),
            )
        if self.dropped:
            logger.warning(
                "%s: skipped %d entries that weren't HTTPS URLs on its hosts",
                self.outlet.name,
                self.dropped,
            )


def describe(error: Exception) -> str:
    """A short, plain reason for a read failure."""
    if isinstance(error, RobotsDisallowed):
        return "robots.txt disallows it"
    if isinstance(error, Blocked):
        return f"the site refused it with HTTP {error.status}"
    if isinstance(error, NotCached):
        return "it isn't in the cache (offline mode)"
    if isinstance(error, ResponseTooLarge):
        return f"it's larger than the {error.limit:,}-byte limit"
    if isinstance(error, HostNotAllowed):
        return f"refused, {error.reason}"
    if isinstance(error, RequestFailed):
        return f"the request failed ({error.problem}, {error.attempts} attempts)"
    if isinstance(error, etree.XMLSyntaxError):
        return "it isn't well-formed XML"
    return str(error)
