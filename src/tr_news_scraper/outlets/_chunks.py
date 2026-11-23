"""Reading chunked sitemaps: numbered files of articles, in publication order (internal).

Nothing says which file holds which month, so files are dated by their entries, and a range is
kept by position (K1, K2, K4). Everything here works on parsed documents, so it never touches
the network.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
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


def kept(dates: Sequence[datetime | None], start: datetime, end: datetime) -> list[int]:
    """Positions of the entries published in [start, end), in age order (K4).

    The range's block of positions begins at the cut that best separates the entries dated
    before ``start`` (before it) from those dated on or after (after it), and ends at the same
    kind of cut for ``end``, so a few entries out of place can't move a boundary. Then:

    - an entry dated before ``start`` is out: it was published before the range;
    - an entry dated inside the range is in, unless it comes before the block: then it's an
      older article edited during the range;
    - an undated entry, or one dated after the range (edited later), is in when it's inside the
      block.
    """
    first, stop = _cut(dates, start, latest=False), _cut(dates, end, latest=True)
    return [
        position
        for position in range(first, len(dates))
        if _kept(dates[position], position < stop, start, end)
    ]


def _kept(found: datetime | None, inside: bool, start: datetime, end: datetime) -> bool:
    if found is None or found >= end:
        return inside
    return found >= start


def _cut(dates: Sequence[datetime | None], target: datetime, *, latest: bool) -> int:
    """The cut, right after a dated entry (or at 0), with the most entries dated before
    ``target`` before it plus entries dated on or after it after it. Among equally good cuts,
    the earliest or the ``latest``: the block takes in the stretch where a few entries are out
    of place at either end."""
    after = sum(1 for found in dates if found is not None and found >= target)
    best, best_score, before = 0, after, 0
    for position, found in enumerate(dates):
        if found is None:
            continue
        if found < target:
            before += 1
        else:
            after -= 1
        score = before + after
        if score > best_score or (latest and score == best_score):
            best, best_score = position + 1, score
    return best


def months_for(
    dates: Sequence[datetime | None], positions: Sequence[int], start: date, end: date
) -> list[Month]:
    """Each kept entry's month (K4): the month of the earliest date at or after its position,
    which bounds its publication from above, brought within the range's months."""
    first_month, last_month = Month.of(start), Month.of(end - timedelta(days=1))
    bounds: dict[int, datetime | None] = {}
    lowest: datetime | None = None
    for position in range(len(dates) - 1, min(positions, default=len(dates)) - 1, -1):
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


def first_dated_on_or_after(
    count: int,
    date_at: Callable[[int], datetime | None],
    target: datetime,
    *,
    oldest_guess: datetime | None,
    newest_guess: datetime,
) -> int:
    """The position, in age order, of the first of ``count`` chunks dated on or after
    ``target``; ``count`` when none is (K3).

    Interpolation search: the first guess places ``oldest_guess`` (the outlet's earliest month)
    before the first chunk and ``newest_guess`` (today) at the end; later guesses use the dates
    read. A step that doesn't halve the interval switches to bisection, so at most
    ⌈log₂ count⌉ + 3 chunks are read. ``date_at`` reads one chunk's date; an undated chunk
    counts as on or after ``target``, which can only widen what's read.
    """
    low, high = 0, count
    low_date, high_date = oldest_guess, newest_guess
    bisect = oldest_guess is None
    while low < high:
        size = high - low
        probe = (low + high) // 2
        if not bisect and low_date is not None and low_date < target < high_date:
            fraction = (target - low_date) / (high_date - low_date)
            estimate = (low - 1) + fraction * (high - low + 1)
            probe = min(max(round(estimate), low), high - 1)
        found = date_at(probe)
        if found is None or found >= target:
            high = probe
            high_date = high_date if found is None else found
        else:
            low, low_date = probe + 1, found
        if high - low > size // 2:
            bisect = True
    return low


def chunk_ttl(outlet: ChunkedSitemap, position: int, count: int) -> timedelta:
    """How long a chunk, at ``position`` in age order, may be served from the cache (K6).

    A chunk numbered from the newest changes with every new article. Numbered from the oldest,
    only the newest chunk still grows, and the one before it may get late edits.
    """
    if outlet.chunk_order == "newest-first" or position >= count - 1:
        return timedelta(hours=1)
    if position == count - 2:
        return timedelta(days=1)
    return timedelta(days=30)
