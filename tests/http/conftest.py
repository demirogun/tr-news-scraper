"""Fixtures for the http tests: a fake clock and an ``Http`` factory with a throwaway cache."""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from requests_mock import Mocker

from tr_news_scraper._http import Http, HttpConfig

START = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)
PERMISSIVE_HOSTS = ("news.example.com", "other.example.com")


@pytest.fixture(autouse=True)
def _robots_allow_everything(requests_mock: Mocker) -> None:
    """The usual test hosts have no robots.txt (404), which RFC 9309 reads as "allow all"."""
    for host in PERMISSIVE_HOSTS:
        requests_mock.get(f"https://{host}/robots.txt", status_code=404)


class FakeClock:
    """A clock that only moves when the code under test sleeps or a test advances it."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._elapsed = 0.0
        self.sleeps: list[float] = []

    def now(self) -> datetime:
        with self._lock:
            return START + timedelta(seconds=self._elapsed)

    def monotonic(self) -> float:
        with self._lock:
            return self._elapsed

    def sleep(self, seconds: float) -> None:
        with self._lock:
            self.sleeps.append(seconds)
            self._elapsed += max(seconds, 0.0)

    def advance(self, seconds: float) -> None:
        with self._lock:
            self._elapsed += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def make_http(tmp_path: Path, clock: FakeClock) -> Callable[..., Http]:
    """Build an ``Http`` on the fake clock whose cache lives in the test's temp folder."""

    def factory(**config: Any) -> Http:
        config.setdefault("cache_dir", tmp_path / "cache")
        return Http(HttpConfig(**config), clock=clock)

    return factory
