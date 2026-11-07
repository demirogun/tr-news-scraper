"""Cancelling: after ``Http.cancel()`` no new request attempt starts, in any thread."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from requests_mock import Mocker

from tr_news_scraper._http import Cancelled, Http
from tr_news_scraper.errors import TrNewsError

PAGE = "https://news.example.com/haber/1"
ALLOWED = {"news.example.com"}


def page_requests(mock: Mocker) -> int:
    return sum(1 for request in mock.request_history if request.path == "/haber/1")


def test_a_cancelled_client_refuses_new_requests(
    make_http: Callable[..., Http], requests_mock: Mocker
) -> None:
    requests_mock.get(PAGE, text="ok")
    http = make_http()
    assert not http.cancelled
    http.cancel()
    assert http.cancelled
    with pytest.raises(Cancelled, match=r"cancelled before requesting https://news\.example\.com/"):
        http.get(PAGE, allowed_hosts=ALLOWED)
    assert requests_mock.call_count == 0


def test_cancelling_stops_a_request_between_its_attempts(
    make_http: Callable[..., Http], requests_mock: Mocker
) -> None:
    http = make_http()

    def unavailable_then_cancel(request: Any, context: Any) -> str:
        context.status_code = 503
        http.cancel()
        return "busy"

    requests_mock.get(PAGE, text=unavailable_then_cancel)
    with pytest.raises(Cancelled):
        http.get(PAGE, allowed_hosts=ALLOWED)
    assert page_requests(requests_mock) == 1


def test_cancelled_is_not_a_library_error_so_scans_do_not_record_it_as_a_gap() -> None:
    assert not issubclass(Cancelled, TrNewsError)
