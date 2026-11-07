"""Per-host statistics and request logging."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import timedelta

import pytest
from requests_mock import Mocker

from tr_news_scraper._http import CachePolicy, Http
from tr_news_scraper.errors import Blocked, RequestFailed, RobotsDisallowed

SITE = "https://news.example.com"
ALLOWED = {"news.example.com"}


def test_requests_and_cache_hits_are_counted_per_host(
    make_http: Callable[..., Http], requests_mock: Mocker
) -> None:
    requests_mock.get(f"{SITE}/a", text="ok")
    http = make_http()
    policy = CachePolicy(ttl=timedelta(hours=1))
    http.get(f"{SITE}/a", allowed_hosts=ALLOWED, cache=policy)
    http.get(f"{SITE}/a", allowed_hosts=ALLOWED, cache=policy)
    stats = http.stats()["news.example.com"]
    assert (stats.requests, stats.cache_hits) == (2, 1)  # robots.txt + the page; then a hit


def test_retries_blocks_and_failures_are_counted(
    make_http: Callable[..., Http], requests_mock: Mocker
) -> None:
    requests_mock.get(f"{SITE}/flaky", [{"status_code": 503}, {"text": "ok"}])
    requests_mock.get(f"{SITE}/secret", status_code=403)
    requests_mock.get(f"{SITE}/gone", status_code=404)
    http = make_http(min_interval=0)
    http.get(f"{SITE}/flaky", allowed_hosts=ALLOWED)
    with pytest.raises(Blocked):
        http.get(f"{SITE}/secret", allowed_hosts=ALLOWED)
    with pytest.raises(RequestFailed):
        http.get(f"{SITE}/gone", allowed_hosts=ALLOWED)
    stats = http.stats()["news.example.com"]
    assert (stats.retries, stats.blocked, stats.errors) == (1, 1, 1)


def test_robots_blocks_and_the_override_are_recorded(
    make_http: Callable[..., Http], requests_mock: Mocker
) -> None:
    site = "https://strict.example.com"
    requests_mock.get(f"{site}/robots.txt", content=b"User-agent: *\nDisallow: /\n")
    requests_mock.get(f"{site}/a", text="ok")
    obeying = make_http()
    with pytest.raises(RobotsDisallowed):
        obeying.get(f"{site}/a", allowed_hosts={"strict.example.com"})
    assert obeying.stats()["strict.example.com"].robots_blocked == 1
    overriding = make_http(obey_robots=False)
    overriding.get(f"{site}/a", allowed_hosts={"strict.example.com"})
    assert overriding.stats()["strict.example.com"].robots_override is True


def test_stats_are_a_snapshot_not_a_live_view(
    make_http: Callable[..., Http], requests_mock: Mocker
) -> None:
    requests_mock.get(f"{SITE}/a", text="ok")
    http = make_http()
    http.get(f"{SITE}/a", allowed_hosts=ALLOWED)
    snapshot = http.stats()
    http.get(f"{SITE}/a", allowed_hosts=ALLOWED)
    assert snapshot["news.example.com"].requests == 2
    assert http.stats()["news.example.com"].requests == 3


def test_every_request_logs_one_debug_line(
    make_http: Callable[..., Http], requests_mock: Mocker, caplog: pytest.LogCaptureFixture
) -> None:
    requests_mock.get(f"{SITE}/a", text="ok")
    with caplog.at_level(logging.DEBUG, logger="tr_news_scraper.http"):
        make_http().get(f"{SITE}/a", allowed_hosts=ALLOWED)
    lines = [r.getMessage() for r in caplog.records if r.levelno == logging.DEBUG]
    assert len(lines) == 2  # robots.txt and the page
    assert any(f"{SITE}/a" in line and "200" in line and "bytes" in line for line in lines)
