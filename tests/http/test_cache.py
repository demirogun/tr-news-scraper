"""The on-disk cache: TTL, offline mode, what is stored, atomic writes and size limits."""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

import pytest
from requests_mock import Mocker

from tr_news_scraper._http import CachePolicy, Http
from tr_news_scraper._http import cache as cache_module
from tr_news_scraper.errors import NotCached

from .conftest import FakeClock

PAGE = "https://news.example.com/sitemaps/posts-2023-2.xml"
ALLOWED = {"news.example.com"}
DAY = CachePolicy(ttl=timedelta(days=1))


def page_requests(mock: Mocker) -> int:
    return sum(1 for request in mock.request_history if request.path != "/robots.txt")


def test_a_second_get_within_the_ttl_is_served_from_disk(
    make_http: Callable[..., Http], requests_mock: Mocker
) -> None:
    requests_mock.get(PAGE, text="<urlset/>")
    http = make_http()
    first = http.get(PAGE, allowed_hosts=ALLOWED, cache=DAY)
    second = http.get(PAGE, allowed_hosts=ALLOWED, cache=DAY)
    assert page_requests(requests_mock) == 1
    assert (first.from_cache, second.from_cache) == (False, True)
    assert (second.content, second.status, second.url) == (b"<urlset/>", 200, PAGE)


def test_the_cache_survives_a_new_http_instance(
    make_http: Callable[..., Http], requests_mock: Mocker
) -> None:
    requests_mock.get(PAGE, text="ok")
    make_http().get(PAGE, allowed_hosts=ALLOWED, cache=DAY)
    assert make_http().get(PAGE, allowed_hosts=ALLOWED, cache=DAY).from_cache


def test_an_expired_entry_is_fetched_again(
    make_http: Callable[..., Http], requests_mock: Mocker, clock: FakeClock
) -> None:
    requests_mock.get(PAGE, text="ok")
    http = make_http()
    http.get(PAGE, allowed_hosts=ALLOWED, cache=DAY)
    clock.advance(timedelta(days=1, seconds=1).total_seconds())
    assert not http.get(PAGE, allowed_hosts=ALLOWED, cache=DAY).from_cache
    assert page_requests(requests_mock) == 2


def test_without_a_ttl_the_cache_is_written_but_not_read(
    make_http: Callable[..., Http], requests_mock: Mocker
) -> None:
    requests_mock.get(PAGE, text="ok")
    http = make_http()
    http.get(PAGE, allowed_hosts=ALLOWED)
    assert not http.get(PAGE, allowed_hosts=ALLOWED).from_cache
    assert http.get(PAGE, allowed_hosts=ALLOWED, cache=DAY).from_cache


def test_offline_mode_serves_any_age_and_never_touches_the_network(
    make_http: Callable[..., Http], requests_mock: Mocker, clock: FakeClock
) -> None:
    requests_mock.get(PAGE, text="ok")
    http = make_http()
    http.get(PAGE, allowed_hosts=ALLOWED)
    clock.advance(365 * 24 * 3600)
    calls_before = requests_mock.call_count
    assert http.get(PAGE, allowed_hosts=ALLOWED, cache=CachePolicy(offline=True)).from_cache
    assert requests_mock.call_count == calls_before


def test_offline_mode_raises_on_a_miss(
    make_http: Callable[..., Http], requests_mock: Mocker
) -> None:
    with pytest.raises(NotCached):
        make_http().get(PAGE, allowed_hosts=ALLOWED, cache=CachePolicy(offline=True))
    assert requests_mock.call_count == 0


def test_no_store_leaves_nothing_on_disk(
    make_http: Callable[..., Http], requests_mock: Mocker, tmp_path: Path
) -> None:
    requests_mock.get(PAGE, text="ok")
    make_http().get(PAGE, allowed_hosts=ALLOWED, cache=CachePolicy(no_store=True))
    assert not list((tmp_path / "cache").rglob("*.json"))


def test_a_redirected_response_is_cached_under_the_url_that_was_asked_for(
    make_http: Callable[..., Http], requests_mock: Mocker
) -> None:
    requests_mock.get(PAGE, status_code=301, headers={"Location": "/new.xml"})
    requests_mock.get("https://news.example.com/new.xml", text="moved")
    http = make_http()
    http.get(PAGE, allowed_hosts=ALLOWED, cache=DAY)
    cached = http.get(PAGE, allowed_hosts=ALLOWED, cache=DAY)
    assert (cached.from_cache, cached.url, cached.text()) == (
        True,
        "https://news.example.com/new.xml",
        "moved",
    )


def test_close_trims_the_cache_oldest_first(
    make_http: Callable[..., Http], requests_mock: Mocker, clock: FakeClock, tmp_path: Path
) -> None:
    for name in ("a", "b", "c"):
        requests_mock.get(f"https://news.example.com/{name}", content=b"x" * 4000)
    http = make_http(cache_max_bytes=9000)
    for name in ("a", "b", "c"):
        http.get(f"https://news.example.com/{name}", allowed_hosts=ALLOWED)
        clock.advance(60)
    http.close()
    reopened = make_http(cache_max_bytes=9000)
    offline = CachePolicy(offline=True)
    with pytest.raises(NotCached):
        reopened.get("https://news.example.com/a", allowed_hosts=ALLOWED, cache=offline)
    assert reopened.get(
        "https://news.example.com/c", allowed_hosts=ALLOWED, cache=offline
    ).from_cache
    sizes = sum(file.stat().st_size for file in (tmp_path / "cache").rglob("*") if file.is_file())
    assert sizes <= 9000


def test_a_crash_while_writing_leaves_no_entry_behind(
    make_http: Callable[..., Http], requests_mock: Mocker, monkeypatch: pytest.MonkeyPatch
) -> None:
    requests_mock.get(PAGE, text="ok")
    real_replace = os.replace

    def crash_on_metadata(source: str, target: str) -> None:
        if str(target).endswith(".json"):
            raise OSError("disk full")
        real_replace(source, target)

    monkeypatch.setattr(os, "replace", crash_on_metadata)
    http = make_http()
    http.get(PAGE, allowed_hosts=ALLOWED)
    monkeypatch.setattr(os, "replace", real_replace)
    with pytest.raises(NotCached):
        http.get(PAGE, allowed_hosts=ALLOWED, cache=CachePolicy(offline=True))


def test_a_briefly_locked_file_on_windows_is_retried(
    make_http: Callable[..., Http], requests_mock: Mocker, monkeypatch: pytest.MonkeyPatch
) -> None:
    requests_mock.get(PAGE, text="ok")
    real_replace = os.replace
    failures = {"left": 1}

    def locked_once(source: str, target: str) -> None:
        if failures["left"]:
            failures["left"] -= 1
            raise PermissionError("in use by another process")
        real_replace(source, target)

    monkeypatch.setattr(os, "replace", locked_once)
    http = make_http()
    http.get(PAGE, allowed_hosts=ALLOWED)
    assert http.get(PAGE, allowed_hosts=ALLOWED, cache=CachePolicy(offline=True)).from_cache


def test_the_default_cache_folder_is_the_users_cache_directory(
    requests_mock: Mocker, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, clock: FakeClock
) -> None:
    from tr_news_scraper._http import HttpConfig

    monkeypatch.setattr(cache_module, "user_cache_dir", lambda app: str(tmp_path / app))
    requests_mock.get(PAGE, text="ok")
    Http(HttpConfig(), clock=clock, jitter=lambda: 0.0).get(PAGE, allowed_hosts=ALLOWED)
    assert list((tmp_path / "tr-news-scraper").rglob("*.json"))
