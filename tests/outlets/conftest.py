"""Fixtures for the outlets tests: an ``Http`` on a fake clock, and hosts without robots.txt."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from requests_mock import Mocker

from tests.http.conftest import FakeClock
from tr_news_scraper._http import Http, HttpConfig

TEST_HOSTS = ("www.example.com.tr",)


@pytest.fixture(autouse=True)
def _robots_allow_everything(requests_mock: Mocker) -> None:
    """The test host has no robots.txt (404), which RFC 9309 reads as "allow all"."""
    for host in TEST_HOSTS:
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
