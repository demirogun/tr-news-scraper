"""Scanning a chunked sitemap (K3–K6) on a fake archive: 1,000 numbered files of 100 articles,
in every combination of the two declared orders."""

from __future__ import annotations

import math
import re
from collections.abc import Collection
from datetime import date, datetime, time, timedelta
from statistics import median_low
from typing import Any

import pytest
from requests_mock import Mocker

from tr_news_scraper._http import Http
from tr_news_scraper.errors import OutletFailed
from tr_news_scraper.outlets import ChunkedSitemap, Month
from tr_news_scraper.outlets._chunks import chunk_ttl, first_dated_on_or_after, kept
from tr_news_scraper.outlets._dates import ISTANBUL, parse_lastmod
from tr_news_scraper.outlets._model import Gap
from tr_news_scraper.outlets._scan import scan

BASE = "https://www.example.com.tr"
INDEX = f"{BASE}/sitemap.xml"
NS = 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'
CHUNK = re.compile(rf"^{re.escape(BASE)}/sitemap-news-(\d+)\.xml$")
COUNT, SIZE = 1000, 100
FIRST = datetime(2020, 1, 1, tzinfo=ISTANBUL)
STEP = timedelta(minutes=15)
TODAY = date(2026, 11, 7)
EARLIEST = Month(2020, 1)
# An article published in May 2020 and edited in February 2021.
OLD_EDITED = 12_000
ORDERS = [
    ("oldest-first", "oldest-first"),
    ("oldest-first", "newest-first"),
    ("newest-first", "oldest-first"),
    ("newest-first", "newest-first"),
]


def published(article: int) -> datetime:
    return FIRST + article * STEP


def stated(article: int) -> str:
    """The archive's <lastmod>: the publication time, with later edits and bad dates mixed in."""
    if article % 997 == 0:
        return "-001-11-30T00:00:00+02:00"
    if article % 991 == 0:
        return "1970-01-01T00:00:00Z"
    when = published(article)
    if article % 37 == 0:
        when += timedelta(days=40)
    if article == OLD_EDITED:
        when = datetime(2021, 2, 14, 12, tzinfo=ISTANBUL)
    return when.isoformat()


def observed(article: int) -> datetime | None:
    """An article's date as K2 reads it."""
    found = parse_lastmod(stated(article))
    if found is None or found < FIRST:
        return None
    return found


DATES = [observed(article) for article in range(COUNT * SIZE)]
MEDIANS = [
    median_low([d for d in DATES[i * SIZE : (i + 1) * SIZE] if d is not None]) for i in range(COUNT)
]


def article_url(article: int) -> str:
    return f"{BASE}/haber/{article}"


def outlet(chunk_order: str, entry_order: str) -> ChunkedSitemap:
    return ChunkedSitemap(
        id="ornek",
        name="Örnek",
        index=INDEX,
        chunk_file=r"/sitemap-news-(?P<n>\d+)\.xml$",
        chunk_order=chunk_order,  # type: ignore[arg-type]
        entry_order=entry_order,  # type: ignore[arg-type]
        earliest=EARLIEST,
    )


def number(position: int, chunk_order: str) -> int:
    """The file number of the chunk at ``position`` in age order."""
    return position + 1 if chunk_order == "oldest-first" else COUNT - position


def serve(
    requests_mock: Mocker, chunk_order: str, entry_order: str, failing: Collection[int] = ()
) -> None:
    """The index and every file, built on request; ``failing`` positions answer 403."""
    locs = [f"{BASE}/sitemap-pages.xml", f"{BASE}/sitemap-tags.xml"]
    locs += [f"{BASE}/sitemap-news-{n}.xml" for n in range(1, COUNT + 1)]
    entries = "".join(f"<sitemap><loc>{loc}</loc></sitemap>" for loc in locs)
    requests_mock.get(
        INDEX, text=f'<?xml version="1.0"?><sitemapindex {NS}>{entries}</sitemapindex>'
    )

    def chunk(request: Any, context: Any) -> str:
        found = CHUNK.match(request.url)
        assert found is not None
        n = int(found[1])
        position = n - 1 if chunk_order == "oldest-first" else COUNT - n
        if position in failing:
            context.status_code = 403
            return ""
        articles = range(position * SIZE, (position + 1) * SIZE)
        ordered = articles if entry_order == "oldest-first" else reversed(articles)
        urls = "".join(
            f"<url><loc>{article_url(a)}</loc><lastmod>{stated(a)}</lastmod></url>" for a in ordered
        )
        return f'<?xml version="1.0"?><urlset {NS}>{urls}</urlset>'

    requests_mock.get(CHUNK, text=chunk)


def chunk_requests(requests_mock: Mocker) -> list[str]:
    return [r.url for r in requests_mock.request_history if CHUNK.match(r.url)]


def expected(start: date, end: date) -> list[str]:
    """What K4 keeps from the whole archive."""
    positions = kept(DATES, _midnight(start), _midnight(end))
    return [article_url(article) for article in positions]


def _midnight(day: date) -> datetime:
    return datetime.combine(day, time(), ISTANBUL)


def first_position(start: date) -> int:
    return next((i for i, d in enumerate(MEDIANS) if d >= _midnight(start)), COUNT)


RANGES = [
    (date(2021, 2, 1), date(2021, 3, 1)),
    (date(2021, 6, 15), date(2021, 6, 16)),
    (date(2019, 12, 15), date(2020, 1, 20)),
    (date(2022, 11, 1), date(2022, 12, 1)),
]


@pytest.mark.parametrize(("chunk_order", "entry_order"), ORDERS)
@pytest.mark.parametrize(("start", "end"), RANGES, ids=["month", "day", "at-start", "at-end"])
def test_a_range_keeps_what_k4_keeps_from_the_whole_archive(
    http: Http,
    requests_mock: Mocker,
    chunk_order: str,
    entry_order: str,
    start: date,
    end: date,
) -> None:
    serve(requests_mock, chunk_order, entry_order)
    found = scan(outlet(chunk_order, entry_order), http, start, end, today=TODAY)
    candidates = list(found)
    assert [c.url for c in candidates] == expected(start, end)
    assert {c.month for c in candidates} <= set(Month.span(start, end))
    requested = chunk_requests(requests_mock)
    assert len(requested) == len(set(requested)), "a file was requested twice"
    spanned = {int(c.url.rsplit("/", 1)[1]) // SIZE for c in candidates}
    bound = math.ceil(math.log2(COUNT)) + 3
    assert len(requested) <= bound + len(spanned) + 2


@pytest.mark.parametrize(("chunk_order", "entry_order"), ORDERS)
def test_the_range_holds_its_articles_and_almost_nothing_else(
    http: Http, requests_mock: Mocker, chunk_order: str, entry_order: str
) -> None:
    serve(requests_mock, chunk_order, entry_order)
    start, end = date(2021, 2, 1), date(2021, 3, 1)
    urls = {c.url for c in scan(outlet(chunk_order, entry_order), http, start, end, today=TODAY)}
    inside = {
        article_url(a)
        for a in range(COUNT * SIZE)
        if _midnight(start) <= published(a) < _midnight(end)
    }
    assert len(inside - urls) <= 0.01 * len(inside)
    assert len(urls - inside) <= 0.01 * len(inside)
    # The old article edited inside the range stays out: its position is before the range.
    assert article_url(OLD_EDITED) not in urls


def test_kept_articles_get_the_months_their_neighbours_bound(
    http: Http, requests_mock: Mocker
) -> None:
    serve(requests_mock, "oldest-first", "newest-first")
    found = scan(
        outlet("oldest-first", "newest-first"),
        http,
        date(2021, 1, 15),
        date(2021, 3, 15),
        today=TODAY,
    )
    by_month: dict[Month, int] = {}
    for candidate in found:
        by_month[candidate.month] = by_month.get(candidate.month, 0) + 1
    assert set(by_month) == {Month(2021, 1), Month(2021, 2), Month(2021, 3)}
    assert found.months == [Month(2021, 1), Month(2021, 2), Month(2021, 3)]
    assert found.gaps == []


@pytest.mark.parametrize(("chunk_order", "entry_order"), ORDERS)
def test_a_range_before_the_archive_is_a_before_archive_gap(
    http: Http, requests_mock: Mocker, chunk_order: str, entry_order: str
) -> None:
    serve(requests_mock, chunk_order, entry_order)
    found = scan(
        outlet(chunk_order, entry_order), http, date(2019, 5, 1), date(2019, 7, 1), today=TODAY
    )
    assert list(found) == []
    assert found.gaps == [
        Gap("before-archive", "the archive starts in 2020-01", month=Month(2019, 5)),
        Gap("before-archive", "the archive starts in 2020-01", month=Month(2019, 6)),
    ]


@pytest.mark.parametrize(("chunk_order", "entry_order"), ORDERS)
def test_a_range_after_the_archive_is_an_after_archive_gap(
    http: Http, requests_mock: Mocker, chunk_order: str, entry_order: str
) -> None:
    serve(requests_mock, chunk_order, entry_order)
    found = scan(
        outlet(chunk_order, entry_order), http, date(2023, 3, 1), date(2023, 4, 1), today=TODAY
    )
    assert list(found) == []
    [gap] = found.gaps
    assert (gap.reason, gap.month) == ("after-archive", Month(2023, 3))
    assert gap.detail == "the archive ends in 2022-12"


def test_a_range_across_the_archives_start_reads_the_part_inside(
    http: Http, requests_mock: Mocker
) -> None:
    serve(requests_mock, "oldest-first", "oldest-first")
    found = scan(
        outlet("oldest-first", "oldest-first"),
        http,
        date(2019, 12, 15),
        date(2020, 1, 20),
        today=TODAY,
    )
    assert len(list(found)) > 0
    assert found.gaps == [
        Gap("before-archive", "the archive starts in 2020-01", month=Month(2019, 12))
    ]
    assert found.months == [Month(2020, 1)]


def probe_positions(target: datetime, oldest_guess: datetime | None) -> tuple[int, list[int]]:
    """The search's answer for ``target`` on the fake archive, and the positions it read."""
    probes: list[int] = []

    def date_at(position: int) -> datetime:
        probes.append(position)
        return MEDIANS[position]

    found = first_dated_on_or_after(
        COUNT, date_at, target, oldest_guess=oldest_guess, newest_guess=_midnight(TODAY)
    )
    return found, probes


def test_the_search_reads_at_most_log2_n_plus_3_files() -> None:
    bound = math.ceil(math.log2(COUNT)) + 3
    month = Month(2019, 6)
    while month <= Month(2023, 3):
        found, probes = probe_positions(_midnight(month.start), _midnight(EARLIEST.start))
        assert found == first_position(month.start), month
        assert len(probes) <= bound, (month, len(probes))
        assert len(probes) == len(set(probes))
        month = month.next()


def test_without_an_earliest_month_the_search_bisects() -> None:
    found, probes = probe_positions(_midnight(date(2021, 2, 1)), None)
    assert found == first_position(date(2021, 2, 1))
    assert probes[0] == COUNT // 2
    assert len(probes) <= math.ceil(math.log2(COUNT)) + 1


def test_an_undated_file_counts_as_on_or_after_the_target() -> None:
    dates: list[datetime | None] = [*MEDIANS[:10], None, *MEDIANS[11:20]]
    target = MEDIANS[15]
    found = first_dated_on_or_after(
        20, dates.__getitem__, target, oldest_guess=None, newest_guess=_midnight(TODAY)
    )
    # Bisection meets the undated file first and stops there: more is read, nothing is missed.
    assert found == 10


def test_a_file_the_search_needs_that_fails_makes_the_range_a_gap(
    http: Http, requests_mock: Mocker
) -> None:
    serve(requests_mock, "oldest-first", "oldest-first", failing=set(range(380, COUNT)))
    found = scan(
        outlet("oldest-first", "oldest-first"),
        http,
        date(2021, 2, 1),
        date(2021, 4, 1),
        today=TODAY,
    )
    assert list(found) == []
    assert [gap.month for gap in found.gaps] == [Month(2021, 2), Month(2021, 3)]
    assert all(gap.reason == "blocked" for gap in found.gaps)
    assert all("needed to find the range" in gap.detail for gap in found.gaps)
    assert found.months == []


def test_a_file_inside_the_range_that_fails_is_a_gap_and_the_rest_still_counts(
    http: Http, requests_mock: Mocker
) -> None:
    start, end = date(2021, 2, 1), date(2021, 3, 1)
    broken = first_position(start) + 10
    serve(requests_mock, "oldest-first", "oldest-first", failing={broken})
    found = scan(outlet("oldest-first", "oldest-first"), http, start, end, today=TODAY)
    urls = [c.url for c in found]
    lost = {article_url(a) for a in range(broken * SIZE, (broken + 1) * SIZE)}
    assert set(urls) == set(expected(start, end)) - lost
    [gap] = found.gaps
    assert (gap.reason, gap.month) == ("blocked", None)
    assert gap.url == f"{BASE}/sitemap-news-{broken + 1}.xml"
    assert gap.detail.startswith(f"archive file {broken + 1} of 1000 couldn't be read")
    assert found.months == []


def test_an_index_that_fails_or_lists_no_numbered_file_fails_the_outlet(
    http: Http, requests_mock: Mocker
) -> None:
    requests_mock.get(INDEX, status_code=404)
    with pytest.raises(OutletFailed, match="its sitemap index couldn't be read"):
        list(
            scan(
                outlet("oldest-first", "oldest-first"),
                http,
                date(2021, 2, 1),
                date(2021, 3, 1),
                today=TODAY,
            )
        )
    requests_mock.get(INDEX, text=f'<?xml version="1.0"?><sitemapindex {NS}></sitemapindex>')
    with pytest.raises(OutletFailed, match="lists no numbered files"):
        list(
            scan(
                outlet("oldest-first", "oldest-first"),
                http,
                date(2021, 2, 1),
                date(2021, 3, 1),
                today=TODAY,
            )
        )


def test_cache_times_follow_how_each_file_changes() -> None:
    oldest_first = outlet("oldest-first", "newest-first")
    assert chunk_ttl(oldest_first, 999, COUNT) == timedelta(hours=1)
    assert chunk_ttl(oldest_first, 998, COUNT) == timedelta(days=1)
    assert chunk_ttl(oldest_first, 0, COUNT) == timedelta(days=30)
    newest_first = outlet("newest-first", "newest-first")
    assert {chunk_ttl(newest_first, p, COUNT) for p in (0, 500, 999)} == {timedelta(hours=1)}


def test_an_article_listed_in_two_files_is_kept_once(http: Http, requests_mock: Mocker) -> None:
    # Files numbered from the newest shift as articles arrive, so one article can end a file
    # and start the next.
    mini = ChunkedSitemap(
        id="ornek",
        name="Örnek",
        index=INDEX,
        chunk_file=r"/sitemap-news-(?P<n>\d+)\.xml$",
        chunk_order="oldest-first",
        entry_order="oldest-first",
        earliest=Month(2023, 1),
    )
    first = datetime(2023, 1, 1, 12, tzinfo=ISTANBUL)
    files = [range(0, 10), range(9, 20), range(20, 30)]
    locs = [f"{BASE}/sitemap-news-{n}.xml" for n in (1, 2, 3)]
    index = "".join(f"<sitemap><loc>{loc}</loc></sitemap>" for loc in locs)
    requests_mock.get(INDEX, text=f'<?xml version="1.0"?><sitemapindex {NS}>{index}</sitemapindex>')
    for loc, articles in zip(locs, files, strict=True):
        listing = "".join(
            f"<url><loc>{article_url(k)}</loc>"
            f"<lastmod>{(first + timedelta(days=k)).isoformat()}</lastmod></url>"
            for k in articles
        )
        requests_mock.get(loc, text=f'<?xml version="1.0"?><urlset {NS}>{listing}</urlset>')
    found = scan(mini, http, date(2023, 1, 5), date(2023, 1, 25), today=TODAY)
    urls = [c.url for c in found]
    assert urls == [article_url(k) for k in range(4, 24)]
