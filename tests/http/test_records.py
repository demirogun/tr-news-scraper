"""Records: small results kept in the response cache's folder and size limit, such as the text
fetch extracted from a page. They never answer requests, and requests never answer for them."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from requests_mock import Mocker

from tr_news_scraper._http import CachePolicy, Http
from tr_news_scraper.errors import NotCached

from .conftest import FakeClock

PAGE = "https://news.example.com/haber/1"
ALLOWED = {"news.example.com"}


def test_a_stored_record_comes_back(make_http: Callable[..., Http]) -> None:
    http = make_http()
    http.store_record(f"extractor 1\n{PAGE}", b'{"text": "Deprem"}')
    assert http.load_record(f"extractor 1\n{PAGE}") == b'{"text": "Deprem"}'
    assert http.load_record(f"extractor 2\n{PAGE}") is None


def test_records_last_beyond_one_client(make_http: Callable[..., Http]) -> None:
    first = make_http()
    first.store_record("record", b"kept")
    first.close()
    assert make_http().load_record("record") == b"kept"


def test_a_record_never_answers_a_request_for_its_name(
    make_http: Callable[..., Http], requests_mock: Mocker
) -> None:
    http = make_http()
    http.store_record(PAGE, b"a record, not the page")
    with pytest.raises(NotCached):
        http.get(PAGE, allowed_hosts=ALLOWED, cache=CachePolicy(offline=True))
    requests_mock.get(PAGE, text="the page")
    http.get(PAGE, allowed_hosts=ALLOWED)
    assert http.load_record(PAGE) == b"a record, not the page"


def test_records_count_in_the_cache_size_limit(
    make_http: Callable[..., Http], clock: FakeClock
) -> None:
    http = make_http(cache_max_bytes=2_500)
    for name in ("oldest", "middle", "newest"):
        http.store_record(name, b"x" * 1_000)
        clock.advance(60)
    http.close()
    assert http.load_record("oldest") is None
    assert http.load_record("middle") == b"x" * 1_000
    assert http.load_record("newest") == b"x" * 1_000
