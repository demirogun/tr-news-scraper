"""URL safety and redirects: only public HTTPS hosts on the allow list, re-checked on every hop."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from requests_mock import Mocker

from tr_news_scraper._http import Http
from tr_news_scraper._http.safety import check_url
from tr_news_scraper.errors import HostNotAllowed, RequestFailed, RobotsDisallowed

SITE = "https://news.example.com"
ALLOWED = {"news.example.com"}


def requested_hosts(mock: Mocker) -> set[str]:
    return {request.hostname for request in mock.request_history}


def test_user_info_in_a_url_is_refused() -> None:
    with pytest.raises(HostNotAllowed, match="user info"):
        check_url("https://user:secret@news.example.com/a", ALLOWED)


@pytest.mark.parametrize(
    "address", ["10.0.0.1", "127.0.0.1", "169.254.169.254", "192.168.1.1", "[::1]", "[fc00::1]"]
)
def test_private_and_reserved_addresses_are_refused_even_when_allowed(address: str) -> None:
    allowed = {address.strip("[]")}
    with pytest.raises(HostNotAllowed, match="private or reserved"):
        check_url(f"https://{address}/latest/meta-data", allowed)


def test_a_public_address_on_the_allow_list_is_accepted() -> None:
    check_url("https://93.184.215.14/a", {"93.184.215.14"})


def test_hosts_are_compared_in_their_idna_form() -> None:
    check_url("https://BÜCHER.example/a", {"bücher.example"})
    check_url("https://bücher.example/a", {"xn--bcher-kva.example"})


def test_a_trailing_dot_on_the_host_is_ignored() -> None:
    check_url("https://news.example.com./a", ALLOWED)


def test_a_url_without_a_host_is_refused() -> None:
    with pytest.raises(HostNotAllowed, match="no host"):
        check_url("https:///path-only", ALLOWED)


def test_a_redirect_on_the_same_host_is_followed(
    make_http: Callable[..., Http], requests_mock: Mocker
) -> None:
    requests_mock.get(f"{SITE}/eski", status_code=301, headers={"Location": "/yeni"})
    requests_mock.get(f"{SITE}/yeni", text="ok")
    response = make_http().get(f"{SITE}/eski", allowed_hosts=ALLOWED)
    assert (response.url, response.text()) == (f"{SITE}/yeni", "ok")


def test_a_redirect_to_a_host_off_the_list_is_refused_before_it_is_requested(
    make_http: Callable[..., Http], requests_mock: Mocker
) -> None:
    requests_mock.get(
        f"{SITE}/a", status_code=302, headers={"Location": "https://evil.example.com/"}
    )
    with pytest.raises(HostNotAllowed, match=r"evil\.example\.com"):
        make_http().get(f"{SITE}/a", allowed_hosts=ALLOWED)
    assert "evil.example.com" not in requested_hosts(requests_mock)


def test_a_redirect_to_plain_http_is_refused(
    make_http: Callable[..., Http], requests_mock: Mocker
) -> None:
    requests_mock.get(
        f"{SITE}/a", status_code=301, headers={"Location": "http://news.example.com/a"}
    )
    with pytest.raises(HostNotAllowed, match="https"):
        make_http().get(f"{SITE}/a", allowed_hosts=ALLOWED)


def test_a_redirect_into_a_robots_disallowed_path_is_refused(
    make_http: Callable[..., Http], requests_mock: Mocker
) -> None:
    site = "https://strict.example.com"
    requests_mock.get(f"{site}/robots.txt", content=b"User-agent: *\nDisallow: /private/\n")
    requests_mock.get(f"{site}/a", status_code=302, headers={"Location": "/private/x"})
    with pytest.raises(RobotsDisallowed):
        make_http().get(f"{site}/a", allowed_hosts={"strict.example.com"})
    assert all(request.path != "/private/x" for request in requests_mock.request_history)


def test_more_than_five_redirects_fail(
    make_http: Callable[..., Http], requests_mock: Mocker
) -> None:
    for hop in range(7):
        requests_mock.get(f"{SITE}/r{hop}", status_code=302, headers={"Location": f"/r{hop + 1}"})
    with pytest.raises(RequestFailed, match="more than 5 redirects"):
        make_http(min_interval=0).get(f"{SITE}/r0", allowed_hosts=ALLOWED)
    hops = [r.path for r in requests_mock.request_history if r.path != "/robots.txt"]
    assert hops == [f"/r{hop}" for hop in range(6)]


def test_robots_txt_redirects_are_followed_to_another_host(
    make_http: Callable[..., Http], requests_mock: Mocker
) -> None:
    requests_mock.get(
        "https://moved.example.com/robots.txt",
        status_code=301,
        headers={"Location": "https://www.moved.example.com/robots.txt"},
    )
    requests_mock.get(
        "https://www.moved.example.com/robots.txt", content=b"User-agent: *\nDisallow: /\n"
    )
    with pytest.raises(RobotsDisallowed):
        make_http().get("https://moved.example.com/a", allowed_hosts={"moved.example.com"})


def test_a_robots_txt_redirect_loop_counts_as_no_robots_txt(
    make_http: Callable[..., Http], requests_mock: Mocker
) -> None:
    site = "https://loop.example.com"
    requests_mock.get(f"{site}/robots.txt", status_code=302, headers={"Location": "/robots.txt"})
    requests_mock.get(f"{site}/a", text="ok")
    assert (
        make_http(min_interval=0).get(f"{site}/a", allowed_hosts={"loop.example.com"}).text()
        == "ok"
    )


def test_a_robots_txt_redirect_into_a_private_network_blocks_the_host(
    make_http: Callable[..., Http], requests_mock: Mocker
) -> None:
    site = "https://sneaky.example.com"
    requests_mock.get(
        f"{site}/robots.txt", status_code=301, headers={"Location": "https://127.0.0.1/robots.txt"}
    )
    with pytest.raises(RobotsDisallowed):
        make_http().get(f"{site}/a", allowed_hosts={"sneaky.example.com"})
    assert "127.0.0.1" not in requested_hosts(requests_mock)
