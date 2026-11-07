"""Retries: which failures are retried, how long we wait, and when we give up."""

from __future__ import annotations

import io
from collections.abc import Callable
from datetime import timedelta
from email.utils import format_datetime

import pytest
import requests
from requests_mock import Mocker
from urllib3 import HTTPSConnectionPool
from urllib3.exceptions import ProtocolError, ReadTimeoutError

from tr_news_scraper._http import Http
from tr_news_scraper._http.retry import parse_retry_after, retry_delay
from tr_news_scraper.errors import Blocked, RequestFailed

from .conftest import START, FakeClock

PAGE = "https://news.example.com/haber/1"
ALLOWED = {"news.example.com"}


def page_requests(mock: Mocker) -> int:
    return sum(1 for request in mock.request_history if request.path == "/haber/1")


class BrokenBody(io.RawIOBase):
    """A response body that breaks off after the status line arrived, like a stalled server."""

    def __init__(self, error: Exception) -> None:
        self._error = error

    def readable(self) -> bool:
        return True

    def readinto(self, buffer: object) -> int:
        raise self._error


@pytest.mark.parametrize(
    ("status", "attempt", "expected"), [(503, 1, 2.0), (503, 2, 4.0), (429, 3, 8.0)]
)
def test_backoff_doubles_with_each_attempt(status: int, attempt: int, expected: float) -> None:
    assert retry_delay(status, {}, attempt, now=START, jitter=lambda: 0.0) == expected


def test_connection_errors_are_retried_like_server_errors() -> None:
    assert retry_delay(None, {}, 1, now=START, jitter=lambda: 0.25) == 2.25


@pytest.mark.parametrize("status", [400, 404, 410, 401, 403, 451])
def test_client_errors_are_not_retried(status: int) -> None:
    assert retry_delay(status, {}, 1, now=START, jitter=lambda: 0.0) is None


def test_retry_after_seconds_replace_the_backoff() -> None:
    assert retry_delay(503, {"Retry-After": "120"}, 1, now=START, jitter=lambda: 0.0) == 120.0


def test_a_retry_after_longer_than_five_minutes_means_give_up() -> None:
    assert retry_delay(429, {"Retry-After": "600"}, 1, now=START, jitter=lambda: 0.0) is None


def test_retry_after_accepts_an_http_date() -> None:
    later = format_datetime(START + timedelta(seconds=90), usegmt=True)
    assert parse_retry_after(later, now=START) == 90.0


def test_a_retry_after_date_in_the_past_means_no_wait() -> None:
    earlier = format_datetime(START - timedelta(minutes=5), usegmt=True)
    assert parse_retry_after(earlier, now=START) == 0.0


@pytest.mark.parametrize("value", [None, "", "soon", "-5"])
def test_unusable_retry_after_values_are_ignored(value: str | None) -> None:
    assert parse_retry_after(value, now=START) is None


def test_two_server_errors_then_success(
    make_http: Callable[..., Http], requests_mock: Mocker, clock: FakeClock
) -> None:
    requests_mock.get(PAGE, [{"status_code": 503}, {"status_code": 503}, {"text": "ok"}])
    response = make_http(min_interval=0).get(PAGE, allowed_hosts=ALLOWED)
    assert response.text() == "ok"
    assert clock.sleeps == [2.0, 4.0]


def test_jitter_is_added_to_the_backoff(
    make_http: Callable[..., Http], requests_mock: Mocker, clock: FakeClock
) -> None:
    requests_mock.get(PAGE, [{"status_code": 502}, {"text": "ok"}])
    make_http(min_interval=0, jitter=0.5).get(PAGE, allowed_hosts=ALLOWED)
    assert clock.sleeps == [2.5]


def test_a_read_timeout_is_retried(
    make_http: Callable[..., Http], requests_mock: Mocker, clock: FakeClock
) -> None:
    requests_mock.get(PAGE, [{"exc": requests.exceptions.ReadTimeout}, {"text": "ok"}])
    assert make_http(min_interval=0).get(PAGE, allowed_hosts=ALLOWED).text() == "ok"
    assert clock.sleeps == [2.0]


@pytest.mark.parametrize(
    "error",
    [
        ReadTimeoutError(HTTPSConnectionPool("news.example.com"), PAGE, "stalled mid-body"),
        ProtocolError("connection broken"),
    ],
    ids=["read-timeout", "connection-broken"],
)
def test_a_body_that_breaks_off_mid_download_is_retried(
    make_http: Callable[..., Http], requests_mock: Mocker, clock: FakeClock, error: Exception
) -> None:
    requests_mock.get(PAGE, [{"body": BrokenBody(error)}, {"text": "ok"}])
    assert make_http(min_interval=0).get(PAGE, allowed_hosts=ALLOWED).text() == "ok"
    assert clock.sleeps == [2.0]


def test_retry_after_from_the_server_is_honored(
    make_http: Callable[..., Http], requests_mock: Mocker, clock: FakeClock
) -> None:
    requests_mock.get(
        PAGE, [{"status_code": 429, "headers": {"Retry-After": "120"}}, {"text": "ok"}]
    )
    make_http(min_interval=0).get(PAGE, allowed_hosts=ALLOWED)
    assert clock.sleeps == [120.0]


def test_a_retry_after_given_as_a_date_is_honored(
    make_http: Callable[..., Http], requests_mock: Mocker, clock: FakeClock
) -> None:
    when = format_datetime(START + timedelta(seconds=120), usegmt=True)
    requests_mock.get(
        PAGE, [{"status_code": 503, "headers": {"Retry-After": when}}, {"text": "ok"}]
    )
    make_http(min_interval=0).get(PAGE, allowed_hosts=ALLOWED)
    assert clock.sleeps == [120.0]


def test_too_long_a_retry_after_fails_and_says_why(
    make_http: Callable[..., Http], requests_mock: Mocker
) -> None:
    requests_mock.get(PAGE, status_code=503, headers={"Retry-After": "600"})
    with pytest.raises(RequestFailed, match="600"):
        make_http(min_interval=0).get(PAGE, allowed_hosts=ALLOWED)
    assert page_requests(requests_mock) == 1


def test_retries_run_out_after_three(
    make_http: Callable[..., Http], requests_mock: Mocker, clock: FakeClock
) -> None:
    requests_mock.get(PAGE, status_code=503)
    with pytest.raises(RequestFailed) as failure:
        make_http(min_interval=0).get(PAGE, allowed_hosts=ALLOWED)
    assert (failure.value.attempts, failure.value.status) == (4, 503)
    assert clock.sleeps == [2.0, 4.0, 8.0]


@pytest.mark.parametrize("status", [401, 403, 451])
def test_a_refusal_is_never_retried(
    make_http: Callable[..., Http], requests_mock: Mocker, status: int
) -> None:
    requests_mock.get(PAGE, status_code=status)
    with pytest.raises(Blocked) as failure:
        make_http(min_interval=0).get(PAGE, allowed_hosts=ALLOWED)
    assert failure.value.status == status
    assert page_requests(requests_mock) == 1


def test_not_found_fails_at_once(make_http: Callable[..., Http], requests_mock: Mocker) -> None:
    requests_mock.get(PAGE, status_code=404)
    with pytest.raises(RequestFailed) as failure:
        make_http(min_interval=0).get(PAGE, allowed_hosts=ALLOWED)
    assert (failure.value.status, failure.value.attempts) == (404, 1)


def test_a_tls_error_is_not_retried(make_http: Callable[..., Http], requests_mock: Mocker) -> None:
    requests_mock.get(PAGE, exc=requests.exceptions.SSLError)
    with pytest.raises(RequestFailed):
        make_http(min_interval=0).get(PAGE, allowed_hosts=ALLOWED)
    assert page_requests(requests_mock) == 1


def test_retries_are_paced_like_any_other_request(
    make_http: Callable[..., Http], requests_mock: Mocker, clock: FakeClock
) -> None:
    requests_mock.get(PAGE, [{"status_code": 503}, {"text": "ok"}])
    make_http(min_interval=5.0).get(PAGE, allowed_hosts=ALLOWED)
    # robots.txt at t=0, page at t=5 (pacing), backoff 2 s, then 3 s more of pacing.
    assert clock.sleeps == [5.0, 2.0, 3.0]
