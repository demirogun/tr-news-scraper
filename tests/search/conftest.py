"""Fixtures for the search tests: an ``Http`` on a fake clock, and recorded outlet archives."""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from requests_mock import Mocker

from tests.http.conftest import FakeClock
from tr_news_scraper._http import Http, HttpConfig
from tr_news_scraper.outlets import MonthlySitemap, builtin, get

RECORDED = Path(__file__).parents[1] / "outlets" / "fixtures"
TODAY = date(2026, 11, 7)
TEST_HOST = "www.example.com.tr"
# Each monthly outlet's recorded month file and the URL it came from (see the fixtures' README).
MONTH_FILES = {
    "cumhuriyet": ("2023-02.xml", "https://www.cumhuriyet.com.tr/sitemaps/posts-2023-2.xml"),
    "euronews-tr": ("2023-02.xml", "https://tr.euronews.com/sitemap/articles-2023-02.xml"),
    "trt-haber": ("2023-02.xml", "https://www.trthaber.com/sitemaps/news-2023-02.xml"),
    "star": ("2023-02.xml", "https://www.star.com.tr/sitemaps/posts-2023-02.xml"),
    "aksam": ("2023-02.xml", "https://www.aksam.com.tr/sitemaps/posts-2023-02.xml"),
    "sozcu": ("2024-06.xml", "https://www.sozcu.com.tr/feeds/sitemapposts?year=2024&month=6"),
}
MILLIYET_SEARCH = re.compile(r"https://www\.milliyet\.com\.tr/api/search/")


@pytest.fixture(autouse=True)
def _hosts_have_no_robots_txt(requests_mock: Mocker) -> None:
    """The built-in and test hosts have no robots.txt (404), which RFC 9309 reads as "allow all"."""
    hosts = {host for outlet in builtin() for host in outlet.hosts} | {TEST_HOST}
    for host in hosts:
        requests_mock.get(f"https://{host}/robots.txt", status_code=404)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def http(tmp_path: Path, clock: FakeClock) -> Iterator[Http]:
    """An ``Http`` whose waits take no real time and whose cache lives in the test's folder."""
    client = Http(HttpConfig(cache_dir=tmp_path / "cache"), clock=clock, jitter=lambda: 0.0)
    yield client
    client.close()


def recorded(outlet_id: str, name: str) -> bytes:
    return (RECORDED / outlet_id / name).read_bytes()


def serve_archive(requests_mock: Mocker, outlet_id: str) -> None:
    """Serve a monthly outlet's recorded index and month file."""
    outlet = get(outlet_id)
    assert isinstance(outlet, MonthlySitemap)
    requests_mock.get(outlet.index, content=recorded(outlet_id, "index.xml"))
    name, url = MONTH_FILES[outlet_id]
    requests_mock.get(url, content=recorded(outlet_id, name))


def serve_milliyet(requests_mock: Mocker) -> None:
    """Milliyet's recorded search: page 1, then page 400's results down to page 400, then empty
    pages, as the real search ends after its newest 10,000 results."""

    def page(request: Any, context: Any) -> str:
        number = int(request.qs["page"][0])
        name = "1" if number == 1 else "400" if number <= 400 else "401"
        return recorded("milliyet", f"deprem-page-{name}.html").decode("utf-8")

    requests_mock.get(MILLIYET_SEARCH, text=page)


def serve_every_outlet(requests_mock: Mocker) -> None:
    for outlet_id in MONTH_FILES:
        serve_archive(requests_mock, outlet_id)
    serve_milliyet(requests_mock)
