"""Per-host pacing: one request in flight per host, starts spaced by the interval or Crawl-delay."""

from __future__ import annotations

import itertools
import threading
import time
from collections.abc import Callable
from typing import Any

from requests_mock import Mocker

from tr_news_scraper._http import Http
from tr_news_scraper._http.clock import SystemClock
from tr_news_scraper._http.pacing import HostPacer

from .conftest import FakeClock

PAGE = "https://news.example.com/haber/1"
ALLOWED = {"news.example.com"}


def record_starts(clock: FakeClock) -> tuple[list[float], Callable[[Any, Any], str]]:
    starts: list[float] = []

    def respond(request: Any, context: Any) -> str:
        starts.append(clock.monotonic())
        return "ok"

    return starts, respond


def gaps(starts: list[float]) -> list[float]:
    return [later - earlier for earlier, later in itertools.pairwise(starts)]


def test_requests_to_one_host_start_at_least_the_interval_apart(
    make_http: Callable[..., Http], requests_mock: Mocker, clock: FakeClock
) -> None:
    starts, respond = record_starts(clock)
    requests_mock.get(PAGE, text=respond)
    http = make_http()
    for _ in range(5):
        http.get(PAGE, allowed_hosts=ALLOWED)
    assert len(starts) == 5
    assert all(gap >= 1.0 for gap in gaps(starts))


def test_a_longer_crawl_delay_in_robots_txt_is_honored(
    make_http: Callable[..., Http], requests_mock: Mocker, clock: FakeClock
) -> None:
    site = "https://slow.example.com"
    requests_mock.get(f"{site}/robots.txt", content=b"User-agent: *\nCrawl-delay: 5\n")
    starts, respond = record_starts(clock)
    requests_mock.get(f"{site}/haber/1", text=respond)
    http = make_http()
    for _ in range(3):
        http.get(f"{site}/haber/1", allowed_hosts={"slow.example.com"})
    assert all(gap >= 5.0 for gap in gaps(starts))


def test_a_zero_interval_never_sleeps(
    make_http: Callable[..., Http], requests_mock: Mocker, clock: FakeClock
) -> None:
    requests_mock.get(PAGE, text="ok")
    http = make_http(min_interval=0)
    for _ in range(3):
        http.get(PAGE, allowed_hosts=ALLOWED)
    assert clock.sleeps == []


# requests-mock runs every mocked request under one global lock, so concurrency is tested on
# HostPacer itself, with real threads and no HTTP.


def test_different_hosts_take_their_turns_in_parallel() -> None:
    pacer = HostPacer(SystemClock())
    a_holds_its_turn = threading.Event()
    b_got_its_turn = threading.Event()
    outcome: dict[str, bool] = {}

    def host_a() -> None:
        with pacer.turn("a.example.com", interval=0):
            a_holds_its_turn.set()
            outcome["b ran while a was in flight"] = b_got_its_turn.wait(timeout=5)

    def host_b() -> None:
        assert a_holds_its_turn.wait(timeout=5)
        with pacer.turn("b.example.com", interval=0):
            b_got_its_turn.set()

    threads = [threading.Thread(target=host_a), threading.Thread(target=host_b)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert outcome == {"b ran while a was in flight": True}


def test_one_host_never_has_two_turns_at_once() -> None:
    pacer = HostPacer(SystemClock())
    lock = threading.Lock()
    in_flight = 0
    peak = 0

    def request() -> None:
        nonlocal in_flight, peak
        with pacer.turn("news.example.com", interval=0):
            with lock:
                in_flight += 1
                peak = max(peak, in_flight)
            time.sleep(0.05)
            with lock:
                in_flight -= 1

    threads = [threading.Thread(target=request) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert peak == 1


def test_turns_on_one_host_start_the_interval_apart_on_the_fake_clock(clock: FakeClock) -> None:
    pacer = HostPacer(clock)
    starts = []
    for _ in range(3):
        with pacer.turn("news.example.com", interval=2.5):
            starts.append(clock.monotonic())
    assert gaps(starts) == [2.5, 2.5]
