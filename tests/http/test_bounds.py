"""Bounds: timeouts per attempt and a cap on the decompressed size of every response."""

from __future__ import annotations

import zlib
from collections.abc import Callable

import pytest
from requests_mock import Mocker

from tr_news_scraper._http import Http
from tr_news_scraper.errors import ResponseTooLarge

PAGE = "https://news.example.com/sitemap.xml"
ALLOWED = {"news.example.com"}
MIB = 1024 * 1024


def gzip_of_zeros(size: int) -> bytes:
    """A gzip stream that expands to ``size`` bytes, built without holding ``size`` in memory."""
    compressor = zlib.compressobj(9, zlib.DEFLATED, 31)
    block = b"\0" * MIB
    parts = [compressor.compress(block) for _ in range(size // MIB)]
    parts.append(compressor.flush())
    return b"".join(parts)


def test_each_attempt_uses_the_connect_and_read_timeouts(
    make_http: Callable[..., Http], requests_mock: Mocker
) -> None:
    requests_mock.get(PAGE, text="ok")
    make_http(connect_timeout=10.0, read_timeout=30.0).get(PAGE, allowed_hosts=ALLOWED)
    assert requests_mock.last_request is not None
    # requests-mock's stubs say int; requests really records the (connect, read) tuple.
    timeout: object = requests_mock.last_request.timeout
    assert timeout == (10.0, 30.0)


def test_a_compression_bomb_is_stopped_at_the_size_cap(
    make_http: Callable[..., Http], requests_mock: Mocker
) -> None:
    bomb = gzip_of_zeros(100 * MIB)
    assert len(bomb) < MIB
    requests_mock.get(PAGE, content=bomb, headers={"Content-Encoding": "gzip"})
    with pytest.raises(ResponseTooLarge) as failure:
        make_http(max_bytes=8 * MIB).get(PAGE, allowed_hosts=ALLOWED)
    assert failure.value.limit == 8 * MIB


def test_a_plain_body_over_the_cap_is_refused(
    make_http: Callable[..., Http], requests_mock: Mocker
) -> None:
    requests_mock.get(PAGE, content=b"x" * (2 * MIB + 1))
    with pytest.raises(ResponseTooLarge):
        make_http(max_bytes=2 * MIB).get(PAGE, allowed_hosts=ALLOWED)


def test_a_body_exactly_at_the_cap_is_accepted(
    make_http: Callable[..., Http], requests_mock: Mocker
) -> None:
    requests_mock.get(PAGE, content=b"x" * MIB)
    assert len(make_http(max_bytes=MIB).get(PAGE, allowed_hosts=ALLOWED).content) == MIB


def test_compressed_bodies_are_returned_decompressed(
    make_http: Callable[..., Http], requests_mock: Mocker
) -> None:
    requests_mock.get(PAGE, content=gzip_of_zeros(MIB), headers={"Content-Encoding": "gzip"})
    assert make_http().get(PAGE, allowed_hosts=ALLOWED).content == b"\0" * MIB


def test_an_oversized_robots_txt_is_read_up_to_500_kib_not_refused(
    make_http: Callable[..., Http], requests_mock: Mocker
) -> None:
    site = "https://big.example.com"
    rules = b"User-agent: *\nDisallow: /private/\n" + b"# filler\n" * (MIB // 9)
    requests_mock.get(f"{site}/robots.txt", content=rules)
    requests_mock.get(f"{site}/haber/1", text="ok")
    http = make_http(max_bytes=MIB // 2)
    assert http.get(f"{site}/haber/1", allowed_hosts={"big.example.com"}).text() == "ok"
