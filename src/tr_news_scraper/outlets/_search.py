"""Site search: reading result pages that list the newest articles first.

A past date range can lie hundreds of pages deep. Because the dates only go down from page to
page, a binary search over page numbers finds the range's first page in about ten requests, where
reading every page could take hundreds. Everything here is pure: pages come from a ``fetch``
function the caller supplies.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import date
from urllib.parse import quote, urljoin

import lxml.html
from lxml import etree

from tr_news_scraper.outlets._dates import parse_day
from tr_news_scraper.outlets._model import SiteSearch


class SearchPageError(ValueError):
    """A result page had results, but not one whose date could be read."""

    def __init__(self, url: str, problem: str) -> None:
        super().__init__(problem)
        self.url = url


@dataclass(frozen=True, slots=True)
class Result:
    """One search result, kept because its link is on the outlet's hosts."""

    url: str
    day: date
    title: str | None
    source: str


@dataclass(frozen=True, slots=True)
class Page:
    """One page of results, in the site's order (newest first)."""

    number: int
    url: str
    results: tuple[Result, ...] = ()
    days: tuple[date, ...] = ()
    """The readable dates of every result on the page, kept or not; they order the pages."""
    items: int = 0
    unreadable: int = 0
    """Results without a readable link or date."""
    dropped: int = 0
    """Results whose link isn't an HTTPS URL on the outlet's hosts."""

    @property
    def empty(self) -> bool:
        """Whether the page has no results at all, which means the results have ended."""
        return self.items == 0

    @property
    def newest(self) -> date:
        return max(self.days)

    @property
    def oldest(self) -> date:
        return min(self.days)


@dataclass(slots=True)
class Outcome:
    """What a search for one keyword reached; filled in while its results are read."""

    exhausted: bool = False
    """The results ended (or ``max_pages`` was reached) before the range's start."""
    oldest_seen: date | None = None
    pages: list[int] = field(default_factory=list)
    """Page numbers fetched, in order."""

    def note(self, page: Page) -> None:
        self.pages.append(page.number)
        if not page.empty and (self.oldest_seen is None or page.oldest < self.oldest_seen):
            self.oldest_seen = page.oldest


def query_text(keyword: str) -> str:
    """The text to send to a site's search: the keyword without matching operators
    (surrounding quotes, a trailing ``*``) and with single spaces."""
    text = keyword.strip()
    if len(text) >= 2 and text[0] == text[-1] == '"':
        text = text[1:-1]
    elif text.endswith("*"):
        text = text[:-1]
    return " ".join(text.split())


def page_url(outlet: SiteSearch, query: str, number: int) -> str:
    """The URL of one result page, with the query percent-encoded."""
    return outlet.url.replace("{query}", quote(query, safe="")).replace("{page}", str(number))


def parse_page(html: str, outlet: SiteSearch, number: int, url: str) -> Page:
    """Read one result page with the outlet's XPaths.

    Links are resolved against the page URL and kept only if they're HTTPS on the outlet's
    hosts. Raises ``SearchPageError`` when the page has results but no readable date.
    """
    if not html.strip():
        return Page(number, url)
    root = lxml.html.fromstring(html, parser=lxml.html.HTMLParser(no_network=True))
    items = [
        item for item in _as_list(outlet.xpaths["item"](root)) if isinstance(item, etree._Element)
    ]
    results: list[Result] = []
    days: list[date] = []
    unreadable = dropped = 0
    for item in items:
        link = _text(outlet.xpaths["link"](item))
        day = parse_day(_text(outlet.xpaths["date"](item)), outlet.date_format)
        if day is not None:
            days.append(day)
        if not link or day is None:
            unreadable += 1
            continue
        absolute = urljoin(url, link.strip())
        if not outlet.accepts(absolute):
            dropped += 1
            continue
        title = _text(outlet.xpaths["title"](item)) if "title" in outlet.xpaths else None
        results.append(Result(absolute, day, _clean(title), url))
    if items and not days:
        raise SearchPageError(url, f"no date on page {number} could be read")
    return Page(number, url, tuple(results), tuple(days), len(items), unreadable, dropped)


def results_in_range(
    fetch: Callable[[int], Page], start: date, end: date, max_pages: int, outcome: Outcome
) -> Iterator[Result]:
    """The results dated ``start <= day < end``, reading as few pages as the order allows.

    Page 1 comes first. When the range is older than page 1, a binary search finds the first
    page that reaches below ``end``; reading then goes forward until a result is older than
    ``start``. ``outcome`` records whether the results ran out before ``start``.
    """
    page = fetch(1)
    outcome.note(page)
    if page.empty or page.newest < start:
        return
    if page.oldest >= end:
        found = _first_page_below(fetch, end, max_pages, outcome)
        if found is None or found.empty:
            outcome.exhausted = True
            return
        page = found
    while True:
        yield from (result for result in page.results if start <= result.day < end)
        if page.oldest < start:
            return
        if page.number >= max_pages:
            outcome.exhausted = True
            return
        page = fetch(page.number + 1)
        outcome.note(page)
        if page.empty:
            outcome.exhausted = True
            return


def _first_page_below(
    fetch: Callable[[int], Page], end: date, max_pages: int, outcome: Outcome
) -> Page | None:
    """The first page after page 1 that is empty or has a result older than ``end``, or
    ``None`` when every page up to ``max_pages`` is newer."""
    low, high = 2, max_pages
    found: Page | None = None
    while low <= high:
        middle = (low + high) // 2
        page = fetch(middle)
        outcome.note(page)
        if page.empty or page.oldest < end:
            found, high = page, middle - 1
        else:
            low = middle + 1
    return found


def _as_list(value: object) -> list[object]:
    return list(value) if isinstance(value, list) else [value]


def _text(value: object) -> str | None:
    """The text an XPath selected: an attribute's value or an element's text content."""
    for selected in _as_list(value):
        if isinstance(selected, etree._Element):
            return "".join(selected.itertext())
        if isinstance(selected, str):
            return str(selected)
    return None


def _clean(text: str | None) -> str | None:
    if text is None:
        return None
    cleaned = unicodedata.normalize("NFC", " ".join(text.split()))
    return cleaned or None
