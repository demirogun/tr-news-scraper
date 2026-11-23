"""Reading chunked sitemaps: numbered files of articles, in publication order (internal).

Nothing says which file holds which month, so files are dated by their entries, and a range is
kept by position (K1, K2, K4). Everything here works on parsed documents, so it never touches
the network.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from statistics import median_low

from lxml import etree

from tr_news_scraper.outlets._dates import ISTANBUL
from tr_news_scraper.outlets._model import ChunkedSitemap, Month
from tr_news_scraper.outlets._sitemaps import Entry, index_prefix, read_entries


@dataclass(frozen=True, slots=True)
class Chunk:
    """One numbered file: its entries in age order, oldest first, each with its date."""

    url: str
    entries: tuple[Entry, ...]
    """The entries whose URLs are HTTPS on the outlet's hosts."""
    dates: tuple[datetime | None, ...]
    """Each entry's date (K2), aligned with ``entries``; ``None`` when it doesn't count."""
    total: int
    """Entries in the file, dropped ones included."""
    dropped: int
    """Entries skipped: no URL, not HTTPS, or not on the outlet's hosts."""

    @property
    def date(self) -> datetime | None:
        """What the file is dated by: the median of its entries' dates, which shrugs off the few
        articles edited later (K2)."""
        known = [found for found in self.dates if found is not None]
        return median_low(known) if known else None

    @property
    def oldest(self) -> datetime | None:
        """The earliest of the entries' dates."""
        return min((found for found in self.dates if found is not None), default=None)

    @property
    def newest(self) -> datetime | None:
        """The latest of the entries' dates."""
        return max((found for found in self.dates if found is not None), default=None)


def listed_chunks(index: etree._Element, outlet: ChunkedSitemap) -> list[str]:
    """The numbered files the index lists, the oldest articles' first (K1).

    Entries that don't match ``chunk_file`` are ignored, such as tags, pages and authors. An
    empty number counts as 1, and a number listed twice keeps its first file.
    """
    prefix = index_prefix(index)
    numbered: dict[int, str] = {}
    for entry in index.iterchildren(f"{prefix}sitemap"):
        url = (entry.findtext(f"{prefix}loc") or "").strip()
        found = outlet.pattern.search(url) if url else None
        number = (found["n"] or "1") if found is not None else ""
        if number.isdigit():
            numbered.setdefault(int(number), url)
    ordered = [numbered[number] for number in sorted(numbered)]
    return ordered if outlet.chunk_order == "oldest-first" else ordered[::-1]


def read_chunk(urlset: etree._Element, outlet: ChunkedSitemap, url: str, *, today: date) -> Chunk:
    """A numbered file's entries in age order, each dated by its Google News publication date
    or else its last edit (K2).

    A date before the outlet's ``earliest`` month, after tomorrow (``today`` is in Türkiye), or
    unreadable doesn't count. Entries whose URLs aren't HTTPS on the outlet's hosts are dropped
    and counted.
    """
    accepted: list[Entry] = []
    total = dropped = 0
    for entry in read_entries(urlset, outlet.titles):
        total += 1
        if not entry.url or not outlet.accepts(entry.url):
            dropped += 1
            continue
        accepted.append(entry)
    if outlet.entry_order == "newest-first":
        accepted.reverse()
    low = None if outlet.earliest is None else _midnight(outlet.earliest.start)
    high = _midnight(today + timedelta(days=2))
    dates = tuple(_date(entry, low, high) for entry in accepted)
    return Chunk(url, tuple(accepted), dates, total, dropped)


def kept(dates: Sequence[datetime | None], start: datetime, end: datetime) -> range:
    """Positions of the entries published in [start, end), in age order (K4): after the last
    entry dated before start, through the last one dated before end.

    Position decides, not an entry's own date: a later edit can't move an article out of the
    range, and an old article edited inside the range stays out.
    """
    first = stop = 0
    for position, found in enumerate(dates):
        if found is None:
            continue
        if found < start:
            first = position + 1
        if found < end:
            stop = position + 1
    return range(first, max(first, stop))


def months_for(
    dates: Sequence[datetime | None], positions: range, start: date, end: date
) -> list[Month]:
    """Each kept entry's month (K4): the month of the earliest date at or after its position,
    which bounds its publication from above, brought within the range's months."""
    first_month, last_month = Month.of(start), Month.of(end - timedelta(days=1))
    bounds: dict[int, datetime | None] = {}
    lowest: datetime | None = None
    for position in range(len(dates) - 1, positions.start - 1, -1):
        found = dates[position]
        if found is not None and (lowest is None or found < lowest):
            lowest = found
        bounds[position] = lowest
    months = []
    for position in positions:
        bound = bounds[position]
        month = last_month if bound is None else Month.of(bound.astimezone(ISTANBUL).date())
        months.append(min(max(month, first_month), last_month))
    return months


def _midnight(day: date) -> datetime:
    return datetime.combine(day, time(), ISTANBUL)


def _date(entry: Entry, low: datetime | None, high: datetime) -> datetime | None:
    found = entry.published or entry.lastmod
    if found is None or found >= high or (low is not None and found < low):
        return None
    return found
