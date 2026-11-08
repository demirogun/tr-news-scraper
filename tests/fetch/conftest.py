"""Fixtures for the fetch tests: an ``Http`` on a fake clock, and the outlets' page skeletons."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from requests_mock import Mocker

from tests.http.conftest import FakeClock
from tr_news_scraper._http import Http, HttpConfig
from tr_news_scraper.outlets import builtin

PAGES = Path(__file__).parent / "fixtures"
HTML = "text/html; charset=utf-8"


@pytest.fixture(autouse=True)
def _hosts_have_no_robots_txt(requests_mock: Mocker) -> None:
    """The built-in hosts have no robots.txt (404), which RFC 9309 reads as "allow all"."""
    for host in {host for outlet in builtin() for host in outlet.hosts}:
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


def skeleton(outlet_id: str) -> str:
    return (PAGES / outlet_id / "page.html").read_text(encoding="utf-8")


def serve_page(requests_mock: Mocker, url: str, outlet_id: str, **response: Any) -> None:
    """Serve an outlet's page skeleton at ``url`` as a UTF-8 web page."""
    requests_mock.get(url, text=skeleton(outlet_id), headers={"Content-Type": HTML}, **response)
