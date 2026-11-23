"""Reading monthly sitemaps: the months an index lists, and the articles in a month's files.

Everything here works on parsed documents, so it never touches the network.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from lxml import etree

from tr_news_scraper.outlets._dates import ISTANBUL, parse_lastmod
from tr_news_scraper.outlets._model import Candidate, Gap, Month, MonthlySitemap

IMAGE_NS = "http://www.google.com/schemas/sitemap-image/1.1"
NEWS_NS = "http://www.google.com/schemas/sitemap-news/0.9"
_IMAGE_TITLE = f"{{{IMAGE_NS}}}image/{{{IMAGE_NS}}}title"
_NEWS_DATE = f"{{{NEWS_NS}}}news/{{{NEWS_NS}}}publication_date"
_NEWS_TITLE = f"{{{NEWS_NS}}}news/{{{NEWS_NS}}}title"


class SitemapError(ValueError):
    """A sitemap isn't the kind of document expected (an index, or a list of URLs)."""


@dataclass(frozen=True, slots=True)
class Entry:
    """One ``<url>`` of a sitemap file, before any check of its URL."""

    url: str
    """The ``<loc>``, without surrounding whitespace; empty when missing."""
    lastmod: datetime | None
    published: datetime | None
    """Google News's ``<news:publication_date>``, timezone-aware (O4a)."""
    title: str | None
    """The headline, from where the outlet says it is; spaces collapsed, NFC."""

    @property
    def day(self) -> date | None:
        """The publication day in Türkiye, when the entry states it."""
        return None if self.published is None else self.published.astimezone(ISTANBUL).date()


@dataclass(frozen=True, slots=True)
class Read:
    """A month whose files the index lists, so they will be read, in index order."""

    month: Month
    urls: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MonthFile:
    """What one month's sitemap file held."""

    candidates: list[Candidate]
    entries: int
    dropped: int
    """Entries skipped: no URL, not HTTPS, or not on the outlet's hosts."""


def listed_months(index: etree._Element, outlet: MonthlySitemap) -> dict[Month, tuple[str, ...]]:
    """The months the sitemap index lists, each with its files' URLs in index order (whitespace
    stripped).

    A month may list several files: parts of one long list, or one file per section (O3a). The
    same URL listed twice counts once. Entries that don't match the outlet's ``month_file``
    pattern are ignored, as are impossible months.
    """
    prefix = _expect(index, "sitemapindex", "a sitemap index")
    months: dict[Month, list[str]] = {}
    for entry in index.iterchildren(f"{prefix}sitemap"):
        url = (entry.findtext(f"{prefix}loc") or "").strip()
        found = outlet.pattern.search(url) if url else None
        if found is None:
            continue
        try:
            month = Month(int(found["year"]), int(found["month"]))
        except ValueError:
            continue
        files = months.setdefault(month, [])
        if url not in files:
            files.append(url)
    return {month: tuple(files) for month, files in months.items()}


def plan_months(listed: Mapping[Month, Sequence[str]], start: date, end: date) -> list[Read | Gap]:
    """For each month the range ``[start, end)`` touches: the file to read, or why there's none.

    A month the index doesn't list is never requested; outlets may answer an error for it.
    """
    if not listed:
        return [
            Gap("not-in-archive", "the archive lists no months", month=month)
            for month in Month.span(start, end)
        ]
    oldest, newest = min(listed), max(listed)
    steps: list[Read | Gap] = []
    for month in Month.span(start, end):
        if month in listed:
            steps.append(Read(month, tuple(listed[month])))
        elif month < oldest:
            steps.append(Gap("before-archive", f"the archive starts in {oldest}", month=month))
        elif month > newest:
            steps.append(Gap("after-archive", f"the archive ends in {newest}", month=month))
        else:
            steps.append(Gap("not-in-archive", f"the archive has no file for {month}", month=month))
    return steps


def read_month_file(
    urlset: etree._Element, outlet: MonthlySitemap, month: Month, source: str
) -> MonthFile:
    """The candidates in one month's sitemap file, in file order.

    URLs lose surrounding whitespace and must be HTTPS on the outlet's hosts; other entries are
    dropped and counted. A Google News publication date gives a candidate its day (O4a), and
    headlines come from where the outlet says they are (``titles``).
    """
    candidates: list[Candidate] = []
    entries = dropped = 0
    for entry in read_entries(urlset, outlet.titles):
        entries += 1
        if not entry.url or not outlet.accepts(entry.url):
            dropped += 1
            continue
        candidates.append(
            Candidate(
                outlet=outlet.id,
                url=entry.url,
                month=month,
                title=entry.title,
                day=entry.day,
                lastmod=entry.lastmod,
                source=source,
            )
        )
    return MonthFile(candidates, entries, dropped)


def read_entries(
    urlset: etree._Element, titles: Literal["image", "news"] | None
) -> Iterator[Entry]:
    """Every ``<url>`` entry of a sitemap file, in file order. Raises ``SitemapError`` for a
    document that isn't a list of URLs."""
    prefix = _expect(urlset, "urlset", "a list of URLs (<urlset>)")
    title_path = {"image": _IMAGE_TITLE, "news": _NEWS_TITLE}.get(titles or "")
    for entry in urlset.iterchildren(f"{prefix}url"):
        yield Entry(
            url=(entry.findtext(f"{prefix}loc") or "").strip(),
            lastmod=parse_lastmod(entry.findtext(f"{prefix}lastmod")),
            published=parse_lastmod(entry.findtext(_NEWS_DATE)),
            title=None if title_path is None else _clean(entry.findtext(title_path)),
        )


def article_id(outlet: MonthlySitemap, url: str) -> int | None:
    """The number ``article_id`` finds in an article URL, or ``None``."""
    if outlet.id_pattern is None:
        return None
    found = outlet.id_pattern.search(url)
    text = found["id"] if found else None
    return int(text) if text and text.isdigit() else None


def _expect(root: etree._Element, name: str, description: str) -> str:
    """Check the root element's name and return the ``{namespace}`` prefix its children use."""
    qname = etree.QName(root)
    if qname.localname != name:
        raise SitemapError(f"expected {description}, found <{qname.localname}>")
    return f"{{{qname.namespace}}}" if qname.namespace else ""


def _clean(text: str | None) -> str | None:
    if text is None:
        return None
    cleaned = unicodedata.normalize("NFC", " ".join(text.split()))
    return cleaned or None
