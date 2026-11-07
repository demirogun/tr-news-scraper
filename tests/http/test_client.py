"""Http.get: honest identity, no cookies, HTTPS and allowed hosts only, careful decoding."""

from __future__ import annotations

import unicodedata
from collections.abc import Callable, Mapping

import pytest
from requests_mock import Mocker

from tr_news_scraper import __version__
from tr_news_scraper._http import Http, HttpConfig
from tr_news_scraper.errors import HostNotAllowed

from .conftest import START, FakeClock

PAGE = "https://news.example.com/haber/deprem-123"
ALLOWED = {"news.example.com"}
USER_AGENT = f"tr-news-scraper/{__version__} (+https://github.com/demirogun/tr-news-scraper)"


def last_headers(mock: Mocker) -> Mapping[str, str]:
    request = mock.last_request
    assert request is not None
    headers: Mapping[str, str] = request.headers
    return headers


def test_requests_carry_the_honest_user_agent(
    make_http: Callable[..., Http], requests_mock: Mocker
) -> None:
    requests_mock.get(PAGE, text="ok")
    make_http().get(PAGE, allowed_hosts=ALLOWED)
    assert last_headers(requests_mock)["User-Agent"] == USER_AGENT


def test_requests_ask_for_turkish_first(
    make_http: Callable[..., Http], requests_mock: Mocker
) -> None:
    requests_mock.get(PAGE, text="ok")
    make_http().get(PAGE, allowed_hosts=ALLOWED)
    assert last_headers(requests_mock)["Accept-Language"] == "tr-TR,tr;q=0.9,en;q=0.5"


def test_a_contact_is_appended_inside_the_user_agent_parentheses(
    make_http: Callable[..., Http], requests_mock: Mocker
) -> None:
    requests_mock.get(PAGE, text="ok")
    make_http(contact="mailto:lab@example.edu").get(PAGE, allowed_hosts=ALLOWED)
    assert last_headers(requests_mock)["User-Agent"] == (
        f"tr-news-scraper/{__version__} "
        "(+https://github.com/demirogun/tr-news-scraper; mailto:lab@example.edu)"
    )


@pytest.mark.parametrize(
    "contact", ["", " lab@example.edu", "a\r\nX-Injected: 1", "lab (x)", "a;b", "ö@example.edu"]
)
def test_unsafe_contacts_are_rejected(contact: str) -> None:
    with pytest.raises(ValueError, match="contact"):
        HttpConfig(contact=contact)


@pytest.mark.parametrize(
    "setting",
    [
        {"min_interval": -1.0},
        {"connect_timeout": 0.0},
        {"read_timeout": -5.0},
        {"max_retries": -1},
        {"max_bytes": 0},
        {"cache_max_bytes": 0},
    ],
)
def test_nonsensical_limits_are_rejected(setting: dict[str, float]) -> None:
    with pytest.raises(ValueError, match=next(iter(setting))):
        HttpConfig(**setting)  # type: ignore[arg-type]


def test_cookies_set_by_a_site_are_never_sent_back(
    make_http: Callable[..., Http], requests_mock: Mocker
) -> None:
    requests_mock.get(PAGE, text="ok", headers={"Set-Cookie": "session=abc; Path=/"})
    http = make_http()
    http.get(PAGE, allowed_hosts=ALLOWED)
    http.get(PAGE, allowed_hosts=ALLOWED)
    assert "Cookie" not in last_headers(requests_mock)


def test_no_referer_is_sent(make_http: Callable[..., Http], requests_mock: Mocker) -> None:
    requests_mock.get(PAGE, text="ok")
    make_http().get(PAGE, allowed_hosts=ALLOWED)
    assert "Referer" not in last_headers(requests_mock)


def test_plain_http_is_refused_before_any_request(
    make_http: Callable[..., Http], requests_mock: Mocker
) -> None:
    with pytest.raises(HostNotAllowed, match="https"):
        make_http().get("http://news.example.com/a", allowed_hosts=ALLOWED)
    assert requests_mock.call_count == 0


def test_hosts_outside_the_allow_list_are_refused_before_any_request(
    make_http: Callable[..., Http], requests_mock: Mocker
) -> None:
    with pytest.raises(HostNotAllowed, match=r"evil\.example\.com"):
        make_http().get("https://evil.example.com/a", allowed_hosts=ALLOWED)
    assert requests_mock.call_count == 0


def test_the_allow_list_ignores_letter_case(
    make_http: Callable[..., Http], requests_mock: Mocker
) -> None:
    requests_mock.get(PAGE, text="ok")
    response = make_http().get(PAGE.replace("news.", "NEWS."), allowed_hosts={"News.Example.com"})
    assert response.status == 200


def test_the_response_records_status_url_headers_and_fetch_time(
    make_http: Callable[..., Http], requests_mock: Mocker, clock: FakeClock
) -> None:
    requests_mock.get(PAGE, text="ok", headers={"Content-Type": "text/plain"})
    response = make_http().get(PAGE, allowed_hosts=ALLOWED)
    assert (response.status, response.url, response.content) == (200, PAGE, b"ok")
    assert response.headers["content-type"] == "text/plain"
    assert response.fetched_at == clock.now()
    assert response.fetched_at > START
    assert response.from_cache is False


def test_text_uses_the_charset_from_the_content_type_header(
    make_http: Callable[..., Http], requests_mock: Mocker
) -> None:
    body = "Gümüşhane'de deprem".encode("windows-1254")
    content_type = {"Content-Type": "text/html; charset=windows-1254"}
    requests_mock.get(PAGE, content=body, headers=content_type)
    assert make_http().get(PAGE, allowed_hosts=ALLOWED).text() == "Gümüşhane'de deprem"


def test_text_falls_back_to_the_xml_declaration(
    make_http: Callable[..., Http], requests_mock: Mocker
) -> None:
    body = '<?xml version="1.0" encoding="ISO-8859-9"?><title>Iğdır</title>'.encode("iso-8859-9")
    requests_mock.get(PAGE, content=body, headers={"Content-Type": "application/xml"})
    assert "Iğdır" in make_http().get(PAGE, allowed_hosts=ALLOWED).text()


def test_text_falls_back_to_the_html_meta_charset(
    make_http: Callable[..., Http], requests_mock: Mocker
) -> None:
    html = '<html><head><meta charset="windows-1254"></head><body>Şırnak</body></html>'
    requests_mock.get(PAGE, content=html.encode("windows-1254"))
    assert "Şırnak" in make_http().get(PAGE, allowed_hosts=ALLOWED).text()


def test_text_defaults_to_utf8_and_replaces_invalid_bytes(
    make_http: Callable[..., Http], requests_mock: Mocker
) -> None:
    requests_mock.get(PAGE, content=b"deprem \xff")
    assert make_http().get(PAGE, allowed_hosts=ALLOWED).text() == "deprem �"


def test_text_ignores_an_unknown_charset_label(
    make_http: Callable[..., Http], requests_mock: Mocker
) -> None:
    content_type = {"Content-Type": "text/html; charset=x-nope"}
    requests_mock.get(PAGE, content=b"sel", headers=content_type)
    assert make_http().get(PAGE, allowed_hosts=ALLOWED).text() == "sel"


def test_text_removes_a_utf8_byte_order_mark(
    make_http: Callable[..., Http], requests_mock: Mocker
) -> None:
    requests_mock.get(PAGE, content=b"\xef\xbb\xbfheyelan")
    assert make_http().get(PAGE, allowed_hosts=ALLOWED).text() == "heyelan"


def test_text_is_normalized_to_nfc(make_http: Callable[..., Http], requests_mock: Mocker) -> None:
    decomposed = unicodedata.normalize("NFD", "Şırnak")
    requests_mock.get(PAGE, content=decomposed.encode())
    text = make_http().get(PAGE, allowed_hosts=ALLOWED).text()
    assert text == unicodedata.normalize("NFC", "Şırnak")
    assert text != decomposed
