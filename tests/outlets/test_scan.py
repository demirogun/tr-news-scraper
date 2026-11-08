"""Scanning a monthly-sitemap outlet: which files are requested, and what happens when one fails."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
from requests_mock import Mocker

from tests.http.conftest import FakeClock
from tr_news_scraper._http import Http, HttpConfig
from tr_news_scraper.errors import OutletFailed, TrNewsError
from tr_news_scraper.outlets import Month, MonthlySitemap
from tr_news_scraper.outlets._model import Gap
from tr_news_scraper.outlets._scan import month_ttl, scan

BASE = "https://www.example.com.tr"
INDEX = f"{BASE}/sitemaps/posts.xml"
OUTLET = MonthlySitemap(
    id="ornek",
    name="Örnek",
    index=INDEX,
    month_file=r"/sitemaps/posts-(?P<year>\d{4})-(?P<month>\d{1,2})\.xml$",
)
TODAY = date(2026, 11, 7)
NS = 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'


def file_url(month: Month) -> str:
    return f"{BASE}/sitemaps/posts-{month.year}-{month.month}.xml"


def index_listing(*months: Month) -> str:
    entries = "".join(f"<sitemap><loc>{file_url(month)}</loc></sitemap>" for month in months)
    return f'<?xml version="1.0"?><sitemapindex {NS}>{entries}</sitemapindex>'


def month_listing(month: Month, count: int = 2) -> str:
    entries = "".join(
        f"<url><loc>{BASE}/gundem/haber-{month}-{n}</loc>"
        f"<lastmod>{month.start}T10:00:00+03:00</lastmod></url>"
        for n in range(count)
    )
    return f'<?xml version="1.0"?><urlset {NS}>{entries}</urlset>'


def serve(requests_mock: Mocker, *listed: Month, skip: tuple[Month, ...] = ()) -> None:
    requests_mock.get(INDEX, text=index_listing(*listed))
    for month in listed:
        if month not in skip:
            requests_mock.get(file_url(month), text=month_listing(month))


def archive_requests(requests_mock: Mocker) -> list[str]:
    return [r.url for r in requests_mock.request_history if not r.url.endswith("/robots.txt")]


JAN, FEB, MAR, APR = Month(2023, 1), Month(2023, 2), Month(2023, 3), Month(2023, 4)


def test_a_scan_reads_only_the_months_the_index_lists(http: Http, requests_mock: Mocker) -> None:
    serve(requests_mock, JAN, MAR)
    requests_mock.get(file_url(FEB), text=month_listing(FEB))  # exists, but isn't listed
    found = scan(OUTLET, http, date(2023, 1, 15), date(2023, 4, 10), today=TODAY)
    urls = [candidate.url for candidate in found]
    assert urls == [f"{BASE}/gundem/haber-2023-01-{n}" for n in range(2)] + [
        f"{BASE}/gundem/haber-2023-03-{n}" for n in range(2)
    ]
    assert archive_requests(requests_mock) == [INDEX, file_url(JAN), file_url(MAR)]
    assert found.months == [JAN, MAR]
    assert found.gaps == [
        Gap("not-in-archive", "the archive has no file for 2023-02", month=FEB),
        Gap("after-archive", "the archive ends in 2023-03", month=APR),
    ]


def test_candidates_carry_their_month_lastmod_and_source(http: Http, requests_mock: Mocker) -> None:
    serve(requests_mock, FEB)
    first = next(iter(scan(OUTLET, http, date(2023, 2, 1), date(2023, 3, 1), today=TODAY)))
    assert (first.outlet, first.month, first.source) == ("ornek", FEB, file_url(FEB))
    assert first.lastmod is not None
    assert first.lastmod.isoformat() == "2023-02-01T10:00:00+03:00"


def test_months_before_the_archive_starts_cost_no_request(
    http: Http, requests_mock: Mocker
) -> None:
    # Sözcü's index starts at 2023-12 and answers 503 for months it doesn't list.
    serve(requests_mock, Month(2023, 12), Month(2024, 1))
    found = scan(OUTLET, http, date(2023, 2, 1), date(2023, 3, 1), today=TODAY)
    assert list(found) == []
    assert archive_requests(requests_mock) == [INDEX]
    assert found.gaps == [Gap("before-archive", "the archive starts in 2023-12", month=FEB)]


@pytest.mark.parametrize(
    ("response", "reason", "detail"),
    [
        ({"status_code": 403}, "blocked", "the site refused it with HTTP 403"),
        ({"status_code": 503}, "failed", "the request failed (HTTP 503, 4 attempts)"),
        ({"status_code": 404}, "failed", "the request failed (HTTP 404, 1 attempt)"),
        ({"text": "<urlset><url>"}, "failed", "it isn't well-formed XML"),
        ({"text": index_listing(JAN)}, "failed", "expected a list of URLs (<urlset>)"),
    ],
)
def test_a_month_that_fails_becomes_a_gap_and_the_scan_goes_on(
    http: Http,
    requests_mock: Mocker,
    response: dict[str, Any],
    reason: str,
    detail: str,
) -> None:
    serve(requests_mock, JAN, FEB, skip=(JAN,))
    requests_mock.get(file_url(JAN), **response)
    found = scan(OUTLET, http, date(2023, 1, 1), date(2023, 3, 1), today=TODAY)
    assert [c.month for c in found] == [FEB, FEB]
    [gap] = found.gaps
    assert (gap.reason, gap.month, gap.url) == (reason, JAN, file_url(JAN))
    assert gap.detail.startswith("the file for 2023-01 couldn't be read: ")
    assert detail in gap.detail


def test_a_month_file_on_another_host_is_refused(http: Http, requests_mock: Mocker) -> None:
    elsewhere = "https://cdn.elsewhere.example/sitemaps/posts-2023-1.xml"
    requests_mock.get(
        INDEX,
        text=f'<?xml version="1.0"?><sitemapindex {NS}><sitemap><loc>{elsewhere}</loc></sitemap>'
        f"<sitemap><loc>{file_url(FEB)}</loc></sitemap></sitemapindex>",
    )
    requests_mock.get(file_url(FEB), text=month_listing(FEB))
    found = scan(OUTLET, http, date(2023, 1, 1), date(2023, 3, 1), today=TODAY)
    assert [c.month for c in found] == [FEB, FEB]
    [gap] = found.gaps
    assert gap.reason == "failed"
    assert "refused, cdn.elsewhere.example is not an allowed host" in gap.detail
    assert elsewhere not in archive_requests(requests_mock)


def test_a_month_file_over_the_size_cap_is_a_gap(
    requests_mock: Mocker, tmp_path: Path, clock: FakeClock
) -> None:
    small = Http(HttpConfig(cache_dir=tmp_path / "cache", max_bytes=400), clock=clock)
    serve(requests_mock, JAN, FEB, skip=(JAN,))
    requests_mock.get(file_url(JAN), text=month_listing(JAN, count=20))
    found = scan(OUTLET, small, date(2023, 1, 1), date(2023, 3, 1), today=TODAY)
    assert [c.month for c in found] == [FEB, FEB]
    assert "larger than the 400-byte limit" in found.gaps[0].detail


def test_a_month_robots_txt_disallows_is_a_robots_gap(http: Http, requests_mock: Mocker) -> None:
    requests_mock.get(
        f"{BASE}/robots.txt", text="User-agent: *\nDisallow: /sitemaps/posts-2023-1.xml\n"
    )
    serve(requests_mock, JAN, FEB)
    found = scan(OUTLET, http, date(2023, 1, 1), date(2023, 3, 1), today=TODAY)
    assert [c.month for c in found] == [FEB, FEB]
    assert [(gap.reason, gap.month) for gap in found.gaps] == [("robots", JAN)]
    assert file_url(JAN) not in archive_requests(requests_mock)


@pytest.mark.parametrize(
    ("response", "why"),
    [
        ({"status_code": 404}, "the request failed"),
        ({"status_code": 403}, "the site refused it with HTTP 403"),
        ({"text": "<html><body>Not a sitemap</body></html>"}, "expected a sitemap index"),
    ],
)
def test_an_unreadable_index_fails_the_whole_outlet(
    http: Http, requests_mock: Mocker, response: dict[str, Any], why: str
) -> None:
    requests_mock.get(INDEX, **response)
    found = scan(OUTLET, http, date(2023, 1, 1), date(2023, 3, 1), today=TODAY)
    with pytest.raises(OutletFailed, match="its sitemap index couldn't be read") as failure:
        list(found)
    assert failure.value.outlet == "ornek"
    assert why in failure.value.reason
    assert isinstance(failure.value, TrNewsError)


def test_an_index_that_lists_no_month_files_fails_the_outlet(
    http: Http, requests_mock: Mocker
) -> None:
    requests_mock.get(
        INDEX,
        text=f'<?xml version="1.0"?><sitemapindex {NS}><sitemap><loc>{BASE}/feeds/pages'
        "</loc></sitemap></sitemapindex>",
    )
    with pytest.raises(OutletFailed, match="lists no monthly files"):
        list(scan(OUTLET, http, date(2023, 1, 1), date(2023, 3, 1), today=TODAY))


def test_an_outlet_whose_every_file_failed_fails_after_recording_the_gaps(
    http: Http, requests_mock: Mocker
) -> None:
    serve(requests_mock, JAN, FEB, skip=(JAN, FEB))
    requests_mock.get(file_url(JAN), status_code=403)
    requests_mock.get(file_url(FEB), status_code=403)
    found = scan(OUTLET, http, date(2023, 1, 1), date(2023, 3, 1), today=TODAY)
    with pytest.raises(OutletFailed, match="none of the files it needed could be read"):
        list(found)
    assert [gap.reason for gap in found.gaps] == ["blocked", "blocked"]


def test_a_range_outside_the_archive_is_not_a_failure(http: Http, requests_mock: Mocker) -> None:
    serve(requests_mock, Month(2023, 12))
    found = scan(OUTLET, http, date(2020, 1, 1), date(2020, 3, 1), today=TODAY)
    assert list(found) == []
    assert [gap.reason for gap in found.gaps] == ["before-archive", "before-archive"]


@pytest.mark.parametrize(
    ("month", "ttl"),
    [
        (Month(2026, 12), timedelta(hours=1)),
        (Month(2026, 11), timedelta(hours=1)),
        (Month(2026, 10), timedelta(days=1)),
        (Month(2026, 9), timedelta(days=30)),
        (Month(1962, 8), timedelta(days=30)),
    ],
)
def test_recent_months_stay_fresh_for_less_time(month: Month, ttl: timedelta) -> None:
    assert month_ttl(month, TODAY) == ttl


def test_a_repeated_scan_rereads_the_index_but_not_an_old_month(
    http: Http, requests_mock: Mocker, clock: FakeClock
) -> None:
    serve(requests_mock, JAN)
    list(scan(OUTLET, http, date(2023, 1, 1), date(2023, 2, 1), today=TODAY))
    clock.advance(2 * 3600)
    list(scan(OUTLET, http, date(2023, 1, 1), date(2023, 2, 1), today=TODAY))
    assert archive_requests(requests_mock) == [INDEX, file_url(JAN), INDEX]


def test_offline_mode_reads_only_the_cache(
    http: Http, requests_mock: Mocker, tmp_path: Path, clock: FakeClock
) -> None:
    serve(requests_mock, JAN, FEB)
    list(scan(OUTLET, http, date(2023, 1, 1), date(2023, 2, 1), today=TODAY))
    offline_http = Http(HttpConfig(cache_dir=tmp_path / "cache"), clock=clock)
    found = scan(
        OUTLET, offline_http, date(2023, 1, 1), date(2023, 3, 1), today=TODAY, offline=True
    )
    assert [c.month for c in found] == [JAN, JAN]
    [gap] = found.gaps
    assert (gap.reason, gap.month) == ("failed", FEB)
    assert "isn't in the cache" in gap.detail
    assert len(archive_requests(requests_mock)) == 2  # only the online scan's index and January


def test_an_offline_scan_without_a_cached_index_fails(http: Http) -> None:
    found = scan(OUTLET, http, date(2023, 1, 1), date(2023, 2, 1), today=TODAY, offline=True)
    with pytest.raises(OutletFailed, match="isn't in the cache"):
        list(found)


def test_a_scan_can_be_iterated_only_once(http: Http, requests_mock: Mocker) -> None:
    serve(requests_mock, JAN)
    found = scan(OUTLET, http, date(2023, 1, 1), date(2023, 2, 1), today=TODAY)
    list(found)
    with pytest.raises(RuntimeError, match="only once"):
        iter(found)


def test_a_scan_needs_a_range_that_isnt_empty(http: Http) -> None:
    with pytest.raises(ValueError, match="must be before"):
        scan(OUTLET, http, date(2023, 2, 1), date(2023, 2, 1), today=TODAY)


def test_a_scan_makes_no_request_until_it_is_iterated(http: Http, requests_mock: Mocker) -> None:
    serve(requests_mock, JAN)
    scan(OUTLET, http, date(2023, 1, 1), date(2023, 2, 1), today=TODAY)
    assert requests_mock.request_history == []


def test_failures_are_warnings_and_boundaries_one_info_line_per_reason(
    http: Http, requests_mock: Mocker, caplog: pytest.LogCaptureFixture
) -> None:
    serve(requests_mock, Month(2022, 12), JAN, skip=(JAN,))
    requests_mock.get(file_url(JAN), status_code=403)
    caplog.set_level(logging.INFO, logger="tr_news_scraper.outlets")
    list(scan(OUTLET, http, date(2022, 6, 1), date(2023, 4, 1), today=TODAY))
    records = [(r.levelname, r.getMessage()) for r in caplog.records if r.name.endswith("outlets")]
    refused = f"the site refused it with HTTP 403 ({file_url(JAN)})"
    assert records == [
        ("WARNING", f"Örnek: the file for 2023-01 couldn't be read: {refused}"),
        ("INFO", "Örnek: 6 month(s) not read (before-archive), 2022-06 to 2022-11"),
        ("INFO", "Örnek: 2 month(s) not read (after-archive), 2023-02 to 2023-03"),
    ]


def test_dropped_entries_are_counted_and_reported(
    http: Http, requests_mock: Mocker, caplog: pytest.LogCaptureFixture
) -> None:
    requests_mock.get(INDEX, text=index_listing(JAN))
    requests_mock.get(
        file_url(JAN),
        text=f'<?xml version="1.0"?><urlset {NS}><url><loc>http://elsewhere.example/a</loc></url>'
        f"<url><loc>{BASE}/gundem/a-1</loc></url></urlset>",
    )
    found = scan(OUTLET, http, date(2023, 1, 1), date(2023, 2, 1), today=TODAY)
    assert [c.url for c in found] == [f"{BASE}/gundem/a-1"]
    assert found.dropped == 1
    assert "skipped 1 entries that weren't HTTPS URLs on its hosts" in caplog.text
