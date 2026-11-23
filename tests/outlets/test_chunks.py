"""Reading chunked sitemaps (K1, K2, K4): numbered files in age order, their dates, and which
entries a date range keeps."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pytest

from tr_news_scraper._http.safety import parse_xml
from tr_news_scraper.outlets import ChunkedSitemap, Month
from tr_news_scraper.outlets._chunks import kept, listed_chunks, months_for, read_chunk
from tr_news_scraper.outlets._dates import ISTANBUL

BASE = "https://www.example.com.tr"
NS = 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'
NEWS_NS = 'xmlns:news="http://www.google.com/schemas/sitemap-news/0.9"'
TODAY = date(2026, 11, 7)
OUTLET: dict[str, Any] = {
    "id": "ornek",
    "name": "Örnek",
    "index": f"{BASE}/sitemap.xml",
    "chunk_file": r"/post-sitemap(?P<n>\d*)\.xml$",
    "chunk_order": "oldest-first",
    "entry_order": "oldest-first",
    "earliest": Month(2013, 12),
}


def outlet(**changes: Any) -> ChunkedSitemap:
    return ChunkedSitemap(**(OUTLET | changes))


def parse(text: str) -> Any:
    return parse_xml(f'<?xml version="1.0"?>{text}'.encode(), max_bytes=10**8, url=f"{BASE}/x.xml")


def index_of(*locs: str) -> Any:
    entries = "".join(f"<sitemap><loc>{loc}</loc></sitemap>" for loc in locs)
    return parse(f"<sitemapindex {NS}>{entries}</sitemapindex>")


def chunk_of(*entries: str) -> Any:
    return parse(f"<urlset {NS} {NEWS_NS}>{''.join(entries)}</urlset>")


def entry(loc: str, lastmod: str | None = None, published: str | None = None) -> str:
    parts = [f"<loc>{loc}</loc>"]
    if lastmod is not None:
        parts.append(f"<lastmod>{lastmod}</lastmod>")
    if published is not None:
        parts.append(
            f"<news:news><news:publication_date>{published}</news:publication_date></news:news>"
        )
    return f"<url>{''.join(parts)}</url>"


def at(day: int, hour: int = 12, month: int = 2) -> datetime:
    return datetime(2023, month, day, hour, tzinfo=ISTANBUL)


# K1: the chunks, in age order


def test_chunks_numbered_oldest_first_are_read_in_their_order() -> None:
    index = index_of(
        f"{BASE}/post-sitemap2.xml",
        f"{BASE}/page-sitemap.xml",
        f"{BASE}/post-sitemap.xml",
        f"{BASE}/post-sitemap10.xml",
        f"{BASE}/author-sitemap.xml",
    )
    assert listed_chunks(index, outlet()) == [
        f"{BASE}/post-sitemap.xml",
        f"{BASE}/post-sitemap2.xml",
        f"{BASE}/post-sitemap10.xml",
    ]


def test_chunks_numbered_newest_first_are_turned_around() -> None:
    index = index_of(f"{BASE}/post-sitemap.xml", f"{BASE}/post-sitemap2.xml")
    assert listed_chunks(index, outlet(chunk_order="newest-first")) == [
        f"{BASE}/post-sitemap2.xml",
        f"{BASE}/post-sitemap.xml",
    ]


def test_a_number_listed_twice_keeps_its_first_file() -> None:
    index = index_of(f"{BASE}/post-sitemap2.xml", f"{BASE}/post-sitemap02.xml")
    assert listed_chunks(index, outlet()) == [f"{BASE}/post-sitemap2.xml"]


def test_an_index_without_numbered_files_lists_no_chunk() -> None:
    assert listed_chunks(index_of(f"{BASE}/page-sitemap.xml"), outlet()) == []


# K2: dates


def test_a_chunk_listed_newest_first_is_read_oldest_first() -> None:
    urlset = chunk_of(
        entry(f"{BASE}/c-3", "2023-02-03T12:00:00+03:00"),
        entry(f"{BASE}/b-2", "2023-02-02T12:00:00+03:00"),
        entry(f"{BASE}/a-1", "2023-02-01T12:00:00+03:00"),
    )
    chunk = read_chunk(urlset, outlet(entry_order="newest-first"), f"{BASE}/c.xml", today=TODAY)
    assert [e.url for e in chunk.entries] == [f"{BASE}/a-1", f"{BASE}/b-2", f"{BASE}/c-3"]
    assert chunk.dates == (at(1), at(2), at(3))
    assert (chunk.date, chunk.oldest, chunk.newest) == (at(2), at(1), at(3))


def test_an_entrys_date_is_its_publication_date_else_its_last_edit() -> None:
    urlset = chunk_of(
        entry(f"{BASE}/a-1", "2023-03-01T10:00:00+03:00", "2023-02-01T12:00:00+03:00"),
        entry(f"{BASE}/b-2", "2023-02-02T12:00:00+03:00"),
    )
    chunk = read_chunk(urlset, outlet(), f"{BASE}/c.xml", today=TODAY)
    assert chunk.dates == (at(1), at(2))


def test_dates_before_earliest_after_tomorrow_or_unreadable_dont_count() -> None:
    urlset = chunk_of(
        entry(f"{BASE}/a-1", "1970-01-01T00:00:00Z"),
        entry(f"{BASE}/b-2", "-001-11-30T00:00:00+02:00"),
        entry(f"{BASE}/c-3", "2023-02-03T12:00:00+03:00"),
        entry(f"{BASE}/d-4", "2026-11-08T23:59:00+03:00"),
        entry(f"{BASE}/e-5", "2026-11-09T00:00:00+03:00"),
        entry(f"{BASE}/f-6"),
    )
    chunk = read_chunk(urlset, outlet(), f"{BASE}/c.xml", today=TODAY)
    assert chunk.dates == (
        None,
        None,
        at(3),
        datetime(2026, 11, 8, 23, 59, tzinfo=ISTANBUL),
        None,
        None,
    )


def test_a_chunks_date_is_the_median_so_a_few_later_edits_dont_move_it() -> None:
    urlset = chunk_of(
        *(entry(f"{BASE}/a-{n}", f"2023-02-{n:02d}T12:00:00+03:00") for n in range(1, 10)),
        entry(f"{BASE}/x-1", "2026-10-01T12:00:00+03:00"),
        entry(f"{BASE}/x-2", "2026-10-02T12:00:00+03:00"),
    )
    chunk = read_chunk(urlset, outlet(), f"{BASE}/c.xml", today=TODAY)
    assert chunk.date == at(6)


def test_a_chunk_without_dates_has_none() -> None:
    chunk = read_chunk(chunk_of(entry(f"{BASE}/a-1")), outlet(), f"{BASE}/c.xml", today=TODAY)
    assert (chunk.date, chunk.oldest, chunk.newest) == (None, None, None)


def test_entries_off_the_outlets_https_hosts_are_dropped_and_counted() -> None:
    urlset = chunk_of(
        entry("http://www.example.com.tr/a-1", "2023-02-01T12:00:00+03:00"),
        entry(f"{BASE}/b-2", "2023-02-02T12:00:00+03:00"),
        entry("", "2023-02-03T12:00:00+03:00"),
    )
    chunk = read_chunk(urlset, outlet(), f"{BASE}/c.xml", today=TODAY)
    assert [e.url for e in chunk.entries] == [f"{BASE}/b-2"]
    assert (chunk.total, chunk.dropped) == (3, 2)


# K4: keeping entries by position

START, END = at(1, 0), at(1, 0, month=3)


@pytest.mark.parametrize(
    ("dates", "positions"),
    [
        # In age order. An entry is kept after the last one dated before the start, through the
        # last one dated before the end, whatever its own date says.
        ([at(1, 0, 1), at(31, 9, 1), at(1, 9), at(10), at(28), at(1, 9, 3)], range(2, 5)),
        # A later edit inside the range stays kept; one after the range does too.
        ([at(31, 9, 1), at(2), at(20, 9, 3), at(5), at(5, 9, 3)], range(1, 4)),
        # An old article edited inside the range stays out: it's before the last entry dated
        # before the start.
        ([at(10, 9, 1), at(15), at(30, 9, 1), at(3), at(4)], range(3, 5)),
        # Undated entries are kept where their neighbours put them.
        ([at(31, 9, 1), None, at(2), None, at(2, 9, 3), None], range(1, 3)),
        # Nothing dated before the start: from the first entry.
        ([at(2), at(3), at(2, 9, 3)], range(0, 2)),
        # Nothing before the end: nothing.
        ([at(2, 9, 3), at(3, 9, 3)], range(0, 0)),
        ([], range(0, 0)),
    ],
)
def test_entries_are_kept_by_position(dates: list[datetime | None], positions: range) -> None:
    assert kept(dates, START, END) == positions


def test_a_kept_entrys_month_is_the_earliest_date_at_or_after_it_within_the_range() -> None:
    dates = [at(31, 9, 1), at(2), at(20, 9, 3), at(5), at(25), None, at(1, 9, 3), at(3, 9, 3)]
    positions = kept(dates, at(1, 0), at(1, 0, month=4))
    assert positions == range(1, 8)
    feb, mar = Month(2023, 2), Month(2023, 3)
    assert months_for(dates, positions, date(2023, 2, 1), date(2023, 4, 1)) == [
        feb,
        feb,
        feb,
        feb,
        mar,
        mar,
        mar,
    ]
    # Bounds outside the range's months are brought back inside it.
    early = [at(20, 9, 1), at(25, 9, 1)]
    assert months_for(early, range(0, 2), date(2023, 2, 1), date(2023, 3, 1)) == [feb, feb]


def test_an_entry_with_no_date_after_it_gets_the_ranges_last_month() -> None:
    dates: list[datetime | None] = [at(2), None]
    assert months_for(dates, range(0, 2), date(2023, 1, 1), date(2023, 3, 1)) == [
        Month(2023, 2),
        Month(2023, 2),
    ]


# K8. Kısa Dalga's full files hold 40,000 entries, about 13 MB. Coverage tracing would roughly
# double the time before 3.14, so the budget runs with coverage paused.
@pytest.mark.no_cover
def test_a_40000_entry_chunk_is_parsed_and_read_in_under_3_seconds() -> None:
    import time

    title = "Kahramanmaraş merkezli depremlerin ardından bölgedeki son durum ve yardım çalışmaları"
    entries = "".join(
        f"<url><loc>{BASE}/gundem/kahramanmaras-merkezli-depremlerin-ardindan-son-durum-{n}</loc>"
        f"<lastmod>2023-02-{1 + n % 28:02d}T{n % 24:02d}:15:00+03:00</lastmod>"
        "<news:news><news:publication><news:name>Örnek</news:name>"
        "<news:language>tr</news:language></news:publication>"
        f"<news:publication_date>2023-02-{1 + n % 28:02d}T{n % 24:02d}:00:00+03:00"
        f"</news:publication_date><news:title>{title} {n}</news:title></news:news></url>"
        for n in range(40_000)
    )
    content = f'<?xml version="1.0"?><urlset {NS} {NEWS_NS}>{entries}</urlset>'.encode()
    assert len(content) > 12_000_000
    news_titles = outlet(titles="news", entry_order="newest-first")
    started = time.perf_counter()
    urlset = parse_xml(content, max_bytes=64 * 1024**2, url=f"{BASE}/sitemap-news-1.xml")
    chunk = read_chunk(urlset, news_titles, f"{BASE}/sitemap-news-1.xml", today=TODAY)
    elapsed = time.perf_counter() - started
    assert len(chunk.entries) == 40_000
    assert chunk.date is not None
    assert elapsed < 3, f"{elapsed:.2f} s"
