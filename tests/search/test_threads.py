"""Running outlets: one thread each, all at once, and Ctrl+C stops them all (S2)."""

from __future__ import annotations

import _thread
import threading
import time
from datetime import datetime
from typing import Any

import pytest
from requests_mock import Mocker

import tr_news_scraper._search as search_module
from tests.search.conftest import recorded, serve_archive
from tr_news_scraper._http import Http
from tr_news_scraper._search import _search
from tr_news_scraper._table import OutletRun
from tr_news_scraper.outlets import Outlet
from tr_news_scraper.outlets._dates import ISTANBUL

NOW = datetime(2026, 11, 7, 12, 0, tzinfo=ISTANBUL)
CUMHURIYET_FILES = "https://www.cumhuriyet.com.tr/sitemaps/posts-2023-{month}.xml"


def worker_threads() -> list[threading.Thread]:
    return [thread for thread in threading.enumerate() if thread.name.startswith("tr-news-scraper")]


def test_outlets_are_scanned_at_the_same_time(http: Http, monkeypatch: pytest.MonkeyPatch) -> None:
    # requests-mock serves one request at a time (it holds a global lock), so the outlets meet
    # at a barrier in a stand-in for each outlet's run instead.
    both = threading.Barrier(2, timeout=5)

    def meet(outlet: Outlet, *args: object, **kwargs: object) -> OutletRun:
        both.wait()  # breaks after 5 s, failing the test, if the outlets run one by one
        return OutletRun(outlet)

    monkeypatch.setattr(search_module, "run_outlet", meet)
    result = _search(
        "deprem",
        "2023-02-01",
        "2023-03-01",
        outlets=["cumhuriyet", "trt-haber"],
        http=http,
        now=NOW,
        offline=False,
    )
    assert list(result.report["outlet"]) == ["cumhuriyet", "trt-haber"]
    assert worker_threads() == []


def test_ctrl_c_stops_every_worker_before_its_next_request(
    http: Http, requests_mock: Mocker
) -> None:
    serve_archive(requests_mock, "cumhuriyet")

    def january(request: Any, context: Any) -> bytes:
        _thread.interrupt_main()
        deadline = time.monotonic() + 5
        while not http.cancelled and time.monotonic() < deadline:
            time.sleep(0.01)
        return recorded("cumhuriyet", "2023-02.xml")

    requests_mock.get(CUMHURIYET_FILES.format(month=1), content=january)
    with pytest.raises(KeyboardInterrupt):
        _search(
            "deprem",
            "2023-01-01",
            "2023-03-01",
            outlets=["cumhuriyet"],
            http=http,
            now=NOW,
            offline=False,
        )
    requested = [request.url for request in requests_mock.request_history]
    assert CUMHURIYET_FILES.format(month=1) in requested
    assert CUMHURIYET_FILES.format(month=2) not in requested
    assert worker_threads() == []


def test_a_bug_in_a_worker_is_raised(
    http: Http, requests_mock: Mocker, monkeypatch: pytest.MonkeyPatch
) -> None:
    serve_archive(requests_mock, "cumhuriyet")

    def broken(*args: object, **kwargs: object) -> None:
        raise ZeroDivisionError("a bug")

    monkeypatch.setattr(search_module, "collect", broken)
    with pytest.raises(ZeroDivisionError, match="a bug"):
        _search(
            "deprem",
            "2023-02-01",
            "2023-03-01",
            outlets=["cumhuriyet"],
            http=http,
            now=NOW,
            offline=False,
        )
    assert worker_threads() == []
