"""Scanning one outlet's archive for a date range: the network side of the outlets module.

Search calls :func:`scan` once per outlet and iterates the result in its own thread. Every
request goes through the shared :class:`~tr_news_scraper._http.Http`, which obeys robots.txt,
paces requests per host and caches responses.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import replace
from datetime import date, datetime, time, timedelta

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
from tr_news_scraper.outlets._chunks import (
    Chunk,
    chunk_ttl,
    first_dated_on_or_after,
    kept,
    listed_chunks,
    months_for,
    read_chunk,
)
from tr_news_scraper.outlets._dates import ISTANBUL
from tr_news_scraper.outlets._model import (
    BOUNDARY_REASONS,
    Candidate,
    ChunkedSitemap,
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
    MonthFile,
    Read,
    SitemapError,
    article_id,
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
        """The archive months whose files were all read (sitemap archives)."""
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
        self._files: dict[str, MonthFile | Exception] = {}
        """Every sitemap file this scan read, by URL: each is requested once (O3b)."""

    def __iter__(self) -> Iterator[Candidate]:
        if self._started:
            raise RuntimeError("a Scan can be iterated only once")
        self._started = True
        return self._run()

    def _run(self) -> Iterator[Candidate]:
        try:
            if isinstance(self.outlet, MonthlySitemap):
                yield from self._monthly(self.outlet)
            elif isinstance(self.outlet, ChunkedSitemap):
                yield from self._chunked(self.outlet)
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
            elif outlet.grouping == "last-edit":
                yield from self._edited_month(outlet, step, listed)
            else:
                candidates, complete = self._month_files(outlet, step)
                yield from candidates
                if complete:
                    self.months.append(step.month)

    def _month_files(self, outlet: MonthlySitemap, step: Read) -> tuple[list[Candidate], bool]:
        """Every file the month lists, in index order, each URL once (O3a), and whether all of
        them were read; a file that fails is a gap naming it."""
        kept: dict[str, Candidate] = {}
        complete = True
        for number, url in enumerate(step.urls, start=1):
            found = self._load(outlet, step.month, url)
            if isinstance(found, Exception):
                part = "the file" if len(step.urls) == 1 else f"file {number} of {len(step.urls)}"
                self._fail(found, f"{part} for {step.month}", month=step.month, url=url)
                complete = False
                continue
            for candidate in found.candidates:
                kept.setdefault(candidate.url, candidate)
        return list(kept.values()), complete

    def _edited_month(
        self, outlet: MonthlySitemap, step: Read, listed: Mapping[Month, Sequence[str]]
    ) -> Iterator[Candidate]:
        """Month M of an archive grouped by last edit (O3b): M's own entries whose article id is
        above the highest in M-1's files, then the entries of M+1's files whose id is in that
        span, up to the highest id in M's files. An entry without an id counts only in its own
        month's file."""
        month = step.month
        own, complete = self._month_files(outlet, step)
        if not own:
            return
        low = None
        before = self._neighbour(outlet, month.previous(), listed)
        if isinstance(before, Exception):
            self._fail(
                before,
                f"the file for {month.previous()}",
                month=month,
                url=_first_file(listed, month.previous()),
                so=f"{month} may include older articles last edited then",
            )
            complete = False
        elif before is not None:
            low = _highest_id(outlet, before)
        kept = [c for c in own if _in_span(article_id(outlet, c.url), low, None, missing=True)]
        after = self._neighbour(outlet, month.next(), listed)
        if isinstance(after, Exception):
            self._fail(
                after,
                f"the file for {month.next()}",
                month=month,
                url=_first_file(listed, month.next()),
                so=f"articles published in {month} and edited later may be missing",
            )
            complete = False
        elif after is not None:
            high = _highest_id(outlet, own)
            seen = {c.url for c in kept}
            kept += [
                replace(c, month=month)
                for c in after
                if c.url not in seen and _in_span(article_id(outlet, c.url), low, high)
            ]
        yield from kept
        if complete:
            self.months.append(month)

    def _neighbour(
        self, outlet: MonthlySitemap, month: Month, listed: Mapping[Month, Sequence[str]]
    ) -> list[Candidate] | Exception | None:
        """A neighbouring month's entries; the first error if one of its files failed; ``None``
        when the index doesn't list the month."""
        if month not in listed:
            return None
        candidates: list[Candidate] = []
        for url in listed[month]:
            found = self._load(outlet, month, url)
            if isinstance(found, Exception):
                return found
            candidates += found.candidates
        return candidates

    def _load(self, outlet: MonthlySitemap, month: Month, url: str) -> MonthFile | Exception:
        """One sitemap file, read once per scan: its candidates, or what stopped it."""
        if url in self._files:
            return self._files[url]
        self._attempts += 1
        found: MonthFile | Exception
        try:
            response = self._get(url, month_ttl(month, self._today), XML_ACCEPT)
            found = read_month_file(response.xml(), outlet, month, url)
        except READ_ERRORS as error:
            found = error
        else:
            self._successes += 1
            self.dropped += found.dropped
            logger.debug(
                "%s: %s has %d entries, kept %d, dropped %d",
                outlet.name,
                url,
                found.entries,
                len(found.candidates),
                found.dropped,
            )
        self._files[url] = found
        return found

    def _chunked(self, outlet: ChunkedSitemap) -> Iterator[Candidate]:
        """Numbered files (K3–K5): find the first file dated on or after the start, read from
        the one before it through the first dated on or after the end, and keep the entries
        between them by position."""
        try:
            index = self._get(outlet.index, INDEX_TTL, XML_ACCEPT).xml()
            urls = listed_chunks(index, outlet)
        except READ_ERRORS as error:
            raise OutletFailed(
                outlet.id, f"its sitemap index couldn't be read: {describe(error)}"
            ) from error
        if not urls:
            raise OutletFailed(outlet.id, "its sitemap index lists no numbered files")
        archive = _Archive(self, outlet, urls)
        start, end = _midnight(self._start), _midnight(self._end)
        oldest_guess = None if outlet.earliest is None else _midnight(outlet.earliest.start)
        try:
            first = first_dated_on_or_after(
                len(urls),
                archive.date_at,
                start,
                oldest_guess=oldest_guess,
                newest_guess=_midnight(self._today),
            )
        except _Unreadable as failed:
            for month in Month.span(self._start, self._end):
                self._fail(
                    failed.error,
                    f"{archive.name(failed.position)}, needed to find the range,",
                    month=month,
                    url=urls[failed.position],
                )
            return
        window: list[Chunk] = []
        for position in range(max(first - 1, 0), len(urls)):
            chunk = archive.chunk(position)
            if chunk is None:
                continue
            window.append(chunk)
            if position >= first and chunk.date is not None and chunk.date >= end:
                break
        complete = not archive.failed
        self._chunk_gaps(archive, start, end, complete=complete)
        entries = [(entry, chunk.url) for chunk in window for entry in chunk.entries]
        dates = [found for chunk in window for found in chunk.dates]
        positions = kept(dates, start, end)
        seen: set[str] = set()
        for position, month in zip(
            positions, months_for(dates, positions, self._start, self._end), strict=True
        ):
            entry, source = entries[position]
            if entry.url in seen:
                continue
            seen.add(entry.url)
            yield Candidate(
                outlet=outlet.id,
                url=entry.url,
                month=month,
                title=entry.title,
                day=entry.day,
                lastmod=entry.lastmod,
                source=source,
            )

    def _chunk_gaps(
        self, archive: _Archive, start: datetime, end: datetime, *, complete: bool
    ) -> None:
        """The range's months outside the archive, as far as the files read show (K5), and the
        months read in full."""
        oldest, newest = archive.oldest(), archive.newest()
        for month in Month.span(self._start, self._end):
            begins = max(_midnight(month.start), start)
            ends = min(_midnight(month.next().start), end)
            if oldest is not None and ends <= oldest:
                first = Month.of(oldest.astimezone(ISTANBUL).date())
                self.gaps.append(
                    Gap("before-archive", f"the archive starts in {first}", month=month)
                )
            elif newest is not None and begins > newest:
                last = Month.of(newest.astimezone(ISTANBUL).date())
                self.gaps.append(Gap("after-archive", f"the archive ends in {last}", month=month))
            elif complete:
                self.months.append(month)

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
        so: str | None = None,
    ) -> None:
        reason: GapReason = "failed"
        if isinstance(error, RobotsDisallowed):
            reason = "robots"
        elif isinstance(error, Blocked):
            reason = "blocked"
        detail = f"{what} couldn't be read: {describe(error)}"
        gap = Gap(
            reason,
            detail if so is None else f"{detail}, so {so}",
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


class _Unreadable(Exception):
    """A chunk the search for the range needed couldn't be read."""

    def __init__(self, position: int, error: Exception) -> None:
        super().__init__(position)
        self.position = position
        self.error = error


class _Archive:
    """A chunked archive's files for one scan: each read once, with its cache time (K6)."""

    def __init__(self, scan: Scan, outlet: ChunkedSitemap, urls: Sequence[str]) -> None:
        self._scan = scan
        self._outlet = outlet
        self._urls = urls
        self._read: dict[int, Chunk | Exception] = {}
        self.failed = False
        """Whether a file inside the range couldn't be read."""

    def name(self, position: int) -> str:
        return f"archive file {position + 1} of {len(self._urls)}"

    def date_at(self, position: int) -> datetime | None:
        found = self._load(position)
        if isinstance(found, Exception):
            raise _Unreadable(position, found)
        return found.date

    def chunk(self, position: int) -> Chunk | None:
        """The file at ``position``, or ``None`` after recording why it couldn't be read."""
        found = self._load(position)
        if isinstance(found, Exception):
            self.failed = True
            self._scan._fail(found, self.name(position), url=self._urls[position])
            return None
        return found

    def oldest(self) -> datetime | None:
        """The oldest date in the archive's first file, if it was read."""
        found = self._read.get(0)
        return found.oldest if isinstance(found, Chunk) else None

    def newest(self) -> datetime | None:
        """The newest date in the archive's last file, if it was read."""
        found = self._read.get(len(self._urls) - 1)
        return found.newest if isinstance(found, Chunk) else None

    def _load(self, position: int) -> Chunk | Exception:
        if position in self._read:
            return self._read[position]
        scan, url = self._scan, self._urls[position]
        ttl = chunk_ttl(self._outlet, position, len(self._urls))
        scan._attempts += 1
        found: Chunk | Exception
        try:
            response = scan._get(url, ttl, XML_ACCEPT)
            found = read_chunk(response.xml(), self._outlet, url, today=scan._today)
        except READ_ERRORS as error:
            found = error
        else:
            scan._successes += 1
            scan.dropped += found.dropped
            logger.debug(
                "%s: %s has %d entries, kept %d, dropped %d",
                self._outlet.name,
                url,
                found.total,
                len(found.entries),
                found.dropped,
            )
        self._read[position] = found
        return found


def _midnight(day: date) -> datetime:
    """The start of ``day`` in Türkiye."""
    return datetime.combine(day, time(), ISTANBUL)


def _first_file(listed: Mapping[Month, Sequence[str]], month: Month) -> str | None:
    """The first file a month lists, to name in a gap."""
    files = listed.get(month)
    return files[0] if files else None


def _highest_id(outlet: MonthlySitemap, candidates: Iterable[Candidate]) -> int | None:
    ids = [found for c in candidates if (found := article_id(outlet, c.url)) is not None]
    return max(ids, default=None)


def _in_span(
    found: int | None, low: int | None, high: int | None, *, missing: bool = False
) -> bool:
    """Whether an article id is above ``low`` and at most ``high``, each bound optional; an
    entry without an id counts as ``missing`` says."""
    if found is None:
        return missing
    return (low is None or found > low) and (high is None or found <= high)


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
        attempts = "1 attempt" if error.attempts == 1 else f"{error.attempts} attempts"
        return f"the request failed ({error.problem}, {attempts})"
    if isinstance(error, etree.XMLSyntaxError):
        return "it isn't well-formed XML"
    return str(error)
