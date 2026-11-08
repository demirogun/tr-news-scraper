"""Health checks: is each outlet's archive still where its definition says, and still readable?

The weekly live check and ``coverage(check=True)`` run these. A check reads the archive fresh,
not from the cache, and costs two requests.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from tr_news_scraper._http import Http
from tr_news_scraper.outlets._model import Month, MonthlySitemap, Outlet, SiteSearch
from tr_news_scraper.outlets._scan import HTML_ACCEPT, READ_ERRORS, XML_ACCEPT, describe
from tr_news_scraper.outlets._search import Page, page_url, parse_page
from tr_news_scraper.outlets._sitemaps import listed_months, read_month_file

MIN_SEARCH_RESULTS = 10
MAX_SEARCH_AGE_DAYS = 14


@dataclass(frozen=True, slots=True)
class Health:
    """The result of one outlet's health check."""

    outlet: str
    problems: tuple[str, ...]
    """What's wrong, one sentence each; empty when the outlet is healthy."""
    oldest: Month | None = None
    """Monthly sitemaps: the first month the index lists."""
    newest: Month | None = None
    """Monthly sitemaps: the last month the index lists."""
    sample: int = 0
    """Candidates in last month's file, or kept results on page 1 of the search."""

    @property
    def ok(self) -> bool:
        return not self.problems


def check(outlet: Outlet, http: Http, *, today: date, query: str = "deprem") -> Health:
    """Check that ``outlet``'s archive still works. ``today`` is the date in Europe/Istanbul;
    ``query`` is what a site-search outlet is searched for."""
    if isinstance(outlet, MonthlySitemap):
        return _check_sitemaps(outlet, http, today)
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
    url = listed.get(last_month)
    if url is None:
        problems.append(f"its index doesn't list last month ({last_month})")
    else:
        try:
            response = http.get(url, allowed_hosts=outlet.hosts, accept=XML_ACCEPT)
            found = read_month_file(response.xml(), outlet, last_month, url)
        except READ_ERRORS as error:
            problems.append(f"the file for {last_month} couldn't be read: {describe(error)}")
        else:
            sample = len(found.candidates)
            if found.entries == 0:
                problems.append(f"the file for {last_month} is empty")
            elif found.dropped * 100 > found.entries:
                problems.append(
                    f"{found.dropped} of {found.entries} entries in the file for {last_month} "
                    "aren't HTTPS URLs on its hosts"
                )
            titled = sum(1 for candidate in found.candidates if candidate.title)
            if outlet.titles == "image" and titled * 2 < len(found.candidates):
                problems.append(
                    f"only {titled} of {len(found.candidates)} entries in the file for "
                    f"{last_month} have a headline"
                )
    return Health(outlet.id, tuple(problems), oldest, newest, sample)


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
