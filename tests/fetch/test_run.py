"""One outlet's run (F2, F8, F9): each article is read once, extracted, and kept as a record."""

from __future__ import annotations

import logging
from typing import Any

import pytest
from requests_mock import Mocker

import tr_news_scraper._fetch as fetch_module
from tests.fetch.conftest import HTML, serve_page
from tr_news_scraper._extract import extractor
from tr_news_scraper._fetch import HTML_ACCEPT, FetchRun, fetch_outlet
from tr_news_scraper._http import CachePolicy, Http
from tr_news_scraper.errors import NotCached
from tr_news_scraper.outlets import get

STAR = get("star")
FIRST = "https://www.star.com.tr/yasam/birinci-haber-1/"
SECOND = "https://www.star.com.tr/yasam/ikinci-haber-2/"
ROWS = [(0, FIRST), (1, SECOND)]


def run(http: Http, rows: list[tuple[int, str]] = ROWS, **options: Any) -> FetchRun:
    settings: dict[str, Any] = {"refresh": False, "offline": False, "progress": None}
    return fetch_outlet(STAR, rows, http, **{**settings, **options})


def serve_both(requests_mock: Mocker) -> None:
    serve_page(requests_mock, FIRST, "star")
    serve_page(requests_mock, SECOND, "star")


def page_requests(requests_mock: Mocker) -> int:
    return sum(1 for r in requests_mock.request_history if "/yasam/" in r.url)


def test_each_article_is_downloaded_extracted_and_kept(http: Http, requests_mock: Mocker) -> None:
    serve_both(requests_mock)
    found = run(http)
    assert (found.downloaded, found.cached, found.failed) == (2, 0, 0)
    first = found.results[0]
    assert (first.extracted.author, first.extracted.error, first.cached) == ("IHA", None, False)
    assert first.extracted.text is not None
    assert first.fetched_at is not None
    assert first.fetched_at.tzinfo is not None
    assert requests_mock.request_history[-1].headers["Accept"] == HTML_ACCEPT


def test_a_second_run_reuses_the_records_without_a_request(
    http: Http, requests_mock: Mocker
) -> None:
    serve_both(requests_mock)
    first = run(http)
    again = run(http)
    assert (again.downloaded, again.cached, again.failed) == (0, 2, 0)
    assert page_requests(requests_mock) == 2
    assert again.results[0] == type(again.results[0])(
        first.results[0].extracted, first.results[0].fetched_at, cached=True
    )


def test_refresh_downloads_again(http: Http, requests_mock: Mocker) -> None:
    serve_both(requests_mock)
    run(http)
    again = run(http, refresh=True)
    assert (again.downloaded, again.cached) == (2, 0)
    assert page_requests(requests_mock) == 4


def test_offline_reads_only_records(http: Http, requests_mock: Mocker) -> None:
    serve_page(requests_mock, FIRST, "star")
    run(http, [(0, FIRST)])
    offline = run(http, offline=True)
    assert (offline.cached, offline.failed) == (1, 1)
    assert offline.results[1].extracted.error == "it isn't in the cache (offline mode)"
    assert page_requests(requests_mock) == 1


def test_article_pages_never_land_in_the_http_cache(http: Http, requests_mock: Mocker) -> None:
    serve_both(requests_mock)
    run(http)
    with pytest.raises(NotCached):
        http.get(
            FIRST, allowed_hosts=STAR.hosts, accept=HTML_ACCEPT, cache=CachePolicy(offline=True)
        )


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        ({"status_code": 403}, "the site refused it with HTTP 403"),
        ({"status_code": 404}, "the request failed (HTTP 404, 1 attempt)"),
        (
            {"content": b"%PDF-1.7", "headers": {"Content-Type": "application/pdf"}},
            "it isn't a web page (application/pdf)",
        ),
        (
            {"text": "<html><body></body></html>", "headers": {"Content-Type": HTML}},
            "no article text found",
        ),
        (
            {"status_code": 301, "headers": {"Location": "https://uzmanpara.milliyet.com.tr/a"}},
            "refused, uzmanpara.milliyet.com.tr is not an allowed host",
        ),
    ],
    ids=["refused", "gone", "not-html", "empty", "off-host-redirect"],
)
def test_each_failure_has_its_reason_and_is_not_kept(
    http: Http, requests_mock: Mocker, response: dict[str, Any], reason: str
) -> None:
    requests_mock.get(FIRST, **response)
    found = run(http, [(0, FIRST)])
    assert (found.failed, found.results[0].extracted.error) == (1, reason)
    assert http.load_record(f"{extractor()}\n{FIRST}") is None


def test_an_article_robots_txt_disallows_is_never_requested(
    http: Http, requests_mock: Mocker
) -> None:
    requests_mock.get(
        "https://www.star.com.tr/robots.txt", text="User-agent: *\nDisallow: /yasam/\n"
    )
    serve_page(requests_mock, FIRST, "star")
    found = run(http, [(0, FIRST)])
    assert found.results[0].extracted.error == "robots.txt disallows it"
    assert page_requests(requests_mock) == 0


def test_a_damaged_record_is_read_again(http: Http, requests_mock: Mocker) -> None:
    serve_page(requests_mock, FIRST, "star")
    http.store_record(f"{extractor()}\n{FIRST}", b"not a record")
    found = run(http, [(0, FIRST)])
    assert (found.downloaded, found.cached) == (1, 0)


def test_progress_is_reported_after_every_article_and_logged(
    http: Http,
    requests_mock: Mocker,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(fetch_module, "PROGRESS_EVERY", 2)
    serve_both(requests_mock)
    third = "https://www.star.com.tr/yasam/ucuncu-haber-3/"
    serve_page(requests_mock, third, "star")
    calls: list[tuple[str, int, int]] = []
    with caplog.at_level(logging.INFO, logger="tr_news_scraper.fetch"):
        run(
            http,
            [*ROWS, (2, third)],
            progress=lambda outlet, done, total: calls.append((outlet, done, total)),
        )
    assert calls == [("star", 1, 3), ("star", 2, 3), ("star", 3, 3)]
    messages = [r.getMessage() for r in caplog.records if r.name == "tr_news_scraper.fetch"]
    assert messages[0].startswith("Star: 2 of 3 articles read, about ")
    assert messages[0].endswith(" left")
    assert messages[1] == "Star: 3 articles read: 3 downloaded, 0 from the cache, 0 failed"


def test_the_time_left_is_said_in_seconds_minutes_or_hours() -> None:
    assert [fetch_module._duration(s) for s in (0.2, 45, 600, 2_400, 9_000)] == [
        "1 s",
        "45 s",
        "10 min",
        "40 min",
        "2.5 h",
    ]


def test_a_milliyet_article_moved_to_its_section_host_is_read(
    http: Http, requests_mock: Mocker
) -> None:
    moved = "https://www.milliyet.com.tr/uzmanpara/deprem-haberi-7692430"
    section = "https://uzmanpara.milliyet.com.tr/uzmanpara/deprem-haberi-7692430"
    requests_mock.get(moved, status_code=301, headers={"Location": section})
    serve_page(requests_mock, section, "milliyet")
    found = fetch_outlet(
        get("milliyet"), [(0, moved)], http, refresh=False, offline=False, progress=None
    )
    assert found.results[0].extracted.error is None
