"""fetch's outlets run at once but read one page at a time, and Ctrl+C stops them; a second run
resumes (F8, F10)."""

from __future__ import annotations

import _thread
import threading
import time
from datetime import datetime
from typing import Any

import pandas as pd
import pytest
from requests_mock import Mocker

import tr_news_scraper._extract as extract_module
import tr_news_scraper._fetch as fetch_module
from tests.fetch.conftest import HTML, skeleton
from tests.http.conftest import FakeClock
from tr_news_scraper._extract import extract
from tr_news_scraper._fetch import FetchRun, _fetch
from tr_news_scraper._http import Http
from tr_news_scraper.outlets import Outlet
from tr_news_scraper.outlets._dates import ISTANBUL

NOW = datetime(2026, 11, 8, 12, 0, tzinfo=ISTANBUL)
URLS = [f"https://www.star.com.tr/yasam/haber-{n}/" for n in range(1, 4)]


def rows(outlets: list[str], urls: list[str]) -> pd.DataFrame:
    return pd.DataFrame({"outlet": outlets, "url": urls}, dtype="string")


def run(http: Http, articles: pd.DataFrame) -> Any:
    return _fetch(
        articles,
        start=None,
        end=None,
        outlets=None,
        progress=None,
        http=http,
        now=NOW,
        offline=False,
        refresh=False,
    )


def workers() -> list[threading.Thread]:
    return [t for t in threading.enumerate() if t.name.startswith("tr-news-scraper")]


def test_outlets_are_fetched_at_the_same_time(http: Http, monkeypatch: pytest.MonkeyPatch) -> None:
    # requests-mock serves one request at a time, so the outlets meet in a stand-in run.
    both = threading.Barrier(2, timeout=5)

    def meet(outlet: Outlet, *args: object, **kwargs: object) -> FetchRun:
        both.wait()  # breaks after 5 s, failing the test, if the outlets run one by one
        return FetchRun(outlet)

    monkeypatch.setattr(fetch_module, "fetch_outlet", meet)
    articles = rows(["star", "aksam"], ["https://www.star.com.tr/a/", "https://www.aksam.com.tr/b"])
    with pytest.raises(Exception, match="no article could be read"):
        run(http, articles)
    assert workers() == []


def test_pages_are_read_one_at_a_time(monkeypatch: pytest.MonkeyPatch) -> None:
    # trafilatura parses every page with one lxml parser, and lxml then gives every thread that
    # uses it the same string dictionary. Outlet threads reading at once aborted the process
    # (CI, Linux, lxml 6.1.3), so downloads overlap but trafilatura runs in one thread at a time.
    reading = 0
    most = 0
    counting = threading.Lock()
    together = threading.Barrier(4, timeout=5)

    def read(html: str, **settings: object) -> None:
        nonlocal reading, most
        with counting:
            reading += 1
            most = max(most, reading)
        time.sleep(0.05)
        with counting:
            reading -= 1

    def outlet() -> None:
        together.wait()
        extract("<html></html>", "https://www.star.com.tr/yasam/haber-1/")

    monkeypatch.setattr("trafilatura.bare_extraction", read)
    threads = [threading.Thread(target=outlet) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert most == 1


def test_a_pages_trees_are_freed_before_another_page_is_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Freeing a page's lxml trees touches the shared dictionary too.
    freed: list[bool] = []

    class Page:
        title = "Kahramanmaraş'ta deprem"
        author = None
        date = "2023-02-06T04:17:00"
        text = "Örnek metin."

        def __del__(self) -> None:
            freed.append(extract_module.ONE_PAGE_AT_A_TIME.locked())

    monkeypatch.setattr("trafilatura.bare_extraction", lambda html, **settings: Page())
    found = extract("<html></html>", "https://www.star.com.tr/yasam/haber-1/")
    assert found.title == "Kahramanmaraş'ta deprem"
    assert freed == [True]


def test_ctrl_c_stops_before_the_next_article_and_a_rerun_resumes(
    http: Http, requests_mock: Mocker, clock: FakeClock
) -> None:
    def second_page(request: Any, context: Any) -> str:
        context.headers["Content-Type"] = HTML
        _thread.interrupt_main()
        deadline = time.monotonic() + 5
        while not http.cancelled and time.monotonic() < deadline:
            time.sleep(0.01)
        return skeleton("star")

    requests_mock.get(URLS[0], text=skeleton("star"), headers={"Content-Type": HTML})
    requests_mock.get(URLS[1], text=second_page)
    requests_mock.get(URLS[2], text=skeleton("star"), headers={"Content-Type": HTML})
    articles = rows(["star"] * 3, URLS)
    with pytest.raises(KeyboardInterrupt):
        run(http, articles)
    requested = [r.url for r in requests_mock.request_history if "/yasam/" in r.url]
    assert requested == URLS[:2]
    assert workers() == []

    http_again = Http(http.config, clock=clock, jitter=lambda: 0.0)
    try:
        result = run(http_again, articles)
    finally:
        http_again.close()
    requested = [r.url for r in requests_mock.request_history if "/yasam/" in r.url]
    assert requested == [*URLS[:2], URLS[2]]
    assert result.report.loc[0, "cached"] == 2
    assert result.report.loc[0, "downloaded"] == 1
