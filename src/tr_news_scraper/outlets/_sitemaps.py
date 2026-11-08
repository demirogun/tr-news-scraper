"""Reading monthly sitemaps: the months an index lists, and the articles in one month's file.

Everything here works on parsed documents, so it never touches the network.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

from lxml import etree

from tr_news_scraper.outlets._dates import parse_lastmod
from tr_news_scraper.outlets._model import Candidate, Gap, Month, MonthlySitemap

IMAGE_NS = "http://www.google.com/schemas/sitemap-image/1.1"
_IMAGE_TITLE = f"{{{IMAGE_NS}}}image/{{{IMAGE_NS}}}title"


class SitemapError(ValueError):
    """A sitemap isn't the kind of document expected (an index, or a list of URLs)."""


@dataclass(frozen=True, slots=True)
class Read:
    """A month whose file the index lists, so it will be read."""

    month: Month
    url: str


@dataclass(frozen=True, slots=True)
class MonthFile:
    """What one month's sitemap file held."""

    candidates: list[Candidate]
    entries: int
    dropped: int
    """Entries skipped: no URL, not HTTPS, or not on the outlet's hosts."""


def listed_months(index: etree._Element, outlet: MonthlySitemap) -> dict[Month, str]:
    """The months the sitemap index lists, each with its file's URL (whitespace stripped).

    Entries that don't match the outlet's ``month_file`` pattern are ignored, as are impossible
    months. When the index lists a month twice, the first entry wins.
    """
    prefix = _expect(index, "sitemapindex", "a sitemap index")
    months: dict[Month, str] = {}
    for entry in index.iterchildren(f"{prefix}sitemap"):
        url = (entry.findtext(f"{prefix}loc") or "").strip()
        found = outlet.pattern.search(url) if url else None
        if found is None:
            continue
        try:
            month = Month(int(found["year"]), int(found["month"]))
        except ValueError:
            continue
        months.setdefault(month, url)
    return months


def plan_months(listed: Mapping[Month, str], start: date, end: date) -> list[Read | Gap]:
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
            steps.append(Read(month, listed[month]))
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
    dropped and counted. Headlines come from ``<image:title>`` only when the outlet says its
    image titles are headlines.
    """
    prefix = _expect(urlset, "urlset", "a list of URLs (<urlset>)")
    want_titles = outlet.titles == "image"
    candidates: list[Candidate] = []
    entries = dropped = 0
    for entry in urlset.iterchildren(f"{prefix}url"):
        entries += 1
        url = (entry.findtext(f"{prefix}loc") or "").strip()
        if not url or not outlet.accepts(url):
            dropped += 1
            continue
        candidates.append(
            Candidate(
                outlet=outlet.id,
                url=url,
                month=month,
                title=_clean(entry.findtext(_IMAGE_TITLE)) if want_titles else None,
                lastmod=parse_lastmod(entry.findtext(f"{prefix}lastmod")),
                source=source,
            )
        )
    return MonthFile(candidates, entries, dropped)


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
