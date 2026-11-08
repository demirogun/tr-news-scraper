"""robots.txt per RFC 9309: rules, status codes, caching, and how Http.get obeys them."""

from __future__ import annotations

import logging
from collections.abc import Callable

import pytest
import requests
from requests_mock import Mocker

from tr_news_scraper._http import Http
from tr_news_scraper._http.robots import RobotsPolicy
from tr_news_scraper.errors import RobotsDisallowed

from .conftest import FakeClock

SITE = "https://robots.example.com"
SABAH_RULES = b"User-agent: *\nDisallow: /get/arama\nDisallow: *getcandidatetopinfo*\n"


def policy_for(
    clock: FakeClock, status: int | None, body: bytes = b"", fetched: list[str] | None = None
) -> RobotsPolicy:
    def fetch(url: str) -> tuple[int | None, bytes]:
        if fetched is not None:
            fetched.append(url)
        return status, body

    return RobotsPolicy(fetch, clock)


def test_wildcard_rules_block_matching_urls(clock: FakeClock) -> None:
    policy = policy_for(clock, 200, SABAH_RULES)
    assert not policy.allows("https://www.sabah.com.tr/x/getcandidatetopinfo/1")
    assert not policy.allows("https://www.sabah.com.tr/get/arama?query=deprem")
    assert policy.allows("https://www.sabah.com.tr/yasam/deprem-7696423")


def test_end_anchored_rules_match_only_at_the_end(clock: FakeClock) -> None:
    policy = policy_for(clock, 200, b"User-agent: *\nDisallow: /*.pdf$\n")
    assert not policy.allows(f"{SITE}/files/report.pdf")
    assert policy.allows(f"{SITE}/files/report.pdf?page=2")


def test_the_longest_matching_rule_wins_whatever_its_order(clock: FakeClock) -> None:
    policy = policy_for(clock, 200, b"User-agent: *\nDisallow: /api/\nAllow: /api/public/\n")
    assert policy.allows(f"{SITE}/api/public/sitemap.xml")
    assert not policy.allows(f"{SITE}/api/search")


def test_a_group_for_our_product_token_overrides_the_star_group(clock: FakeClock) -> None:
    rules = b"User-agent: *\nDisallow: /\n\nUser-agent: tr-news-scraper\nDisallow: /private/\n"
    policy = policy_for(clock, 200, rules)
    assert policy.allows(f"{SITE}/haber/deprem-1")
    assert not policy.allows(f"{SITE}/private/x")


def test_a_utf8_byte_order_mark_does_not_hide_the_first_rule(clock: FakeClock) -> None:
    policy = policy_for(clock, 200, b"\xef\xbb\xbfUser-agent: *\nDisallow: /private/\n")
    assert not policy.allows(f"{SITE}/private/x")


def test_rules_after_the_first_500_kib_are_ignored(clock: FakeClock) -> None:
    padding = b"# padding line\n" * (500 * 1024 // 15 + 1)
    policy = policy_for(clock, 200, b"User-agent: *\n" + padding + b"Disallow: /late/\n")
    assert policy.allows(f"{SITE}/late/x")


@pytest.mark.parametrize("status", [401, 403, 404, 410])
def test_an_unavailable_robots_txt_allows_everything(clock: FakeClock, status: int) -> None:
    assert policy_for(clock, status).allows(f"{SITE}/any/page")


@pytest.mark.parametrize("status", [None, 429, 500, 503])
def test_an_unreachable_robots_txt_blocks_the_whole_host(
    clock: FakeClock, status: int | None
) -> None:
    assert not policy_for(clock, status).allows(f"{SITE}/any/page")


def test_a_redirect_that_was_never_resolved_counts_as_unavailable(clock: FakeClock) -> None:
    assert policy_for(clock, 301).allows(f"{SITE}/any/page")


def test_crawl_delay_is_reported_for_our_group(clock: FakeClock) -> None:
    policy = policy_for(clock, 200, b"User-agent: *\nCrawl-delay: 5\n")
    assert policy.crawl_delay(f"{SITE}/a") == 5.0
    assert policy_for(clock, 200, b"User-agent: *\nDisallow:\n").crawl_delay(f"{SITE}/a") is None


def test_rules_are_fetched_once_and_kept_for_a_day(clock: FakeClock) -> None:
    fetched: list[str] = []
    policy = policy_for(clock, 404, fetched=fetched)
    policy.allows(f"{SITE}/a")
    clock.advance(24 * 60 * 60 - 1)
    policy.allows(f"{SITE}/b")
    assert fetched == [f"{SITE}/robots.txt"]
    clock.advance(1)
    policy.allows(f"{SITE}/c")
    assert len(fetched) == 2


def test_each_host_has_its_own_rules(clock: FakeClock) -> None:
    fetched: list[str] = []
    policy = policy_for(clock, 404, fetched=fetched)
    policy.allows("https://a.example.com/x")
    policy.allows("https://b.example.com/x")
    assert fetched == ["https://a.example.com/robots.txt", "https://b.example.com/robots.txt"]


def test_http_get_refuses_a_disallowed_url_before_requesting_it(
    make_http: Callable[..., Http], requests_mock: Mocker
) -> None:
    requests_mock.get(f"{SITE}/robots.txt", content=b"User-agent: *\nDisallow: /private/\n")
    with pytest.raises(RobotsDisallowed):
        make_http().get(f"{SITE}/private/page", allowed_hosts={"robots.example.com"})
    assert [request.url for request in requests_mock.request_history] == [f"{SITE}/robots.txt"]


def test_robots_txt_is_requested_with_the_honest_user_agent_once_per_host(
    make_http: Callable[..., Http], requests_mock: Mocker
) -> None:
    requests_mock.get(f"{SITE}/robots.txt", content=b"User-agent: *\nDisallow: /private/\n")
    requests_mock.get(f"{SITE}/haber/1", text="ok")
    http = make_http()
    http.get(f"{SITE}/haber/1", allowed_hosts={"robots.example.com"})
    http.get(f"{SITE}/haber/1", allowed_hosts={"robots.example.com"})
    robots_requests = [r for r in requests_mock.request_history if r.path == "/robots.txt"]
    assert len(robots_requests) == 1
    assert robots_requests[0].headers["User-Agent"] == http.config.user_agent


def test_a_server_error_on_robots_txt_blocks_the_host(
    make_http: Callable[..., Http], requests_mock: Mocker
) -> None:
    requests_mock.get(f"{SITE}/robots.txt", status_code=503)
    with pytest.raises(RobotsDisallowed):
        make_http().get(f"{SITE}/haber/1", allowed_hosts={"robots.example.com"})


def test_a_network_failure_on_robots_txt_blocks_the_host(
    make_http: Callable[..., Http], requests_mock: Mocker
) -> None:
    requests_mock.get(f"{SITE}/robots.txt", exc=requests.exceptions.ConnectTimeout)
    with pytest.raises(RobotsDisallowed):
        make_http().get(f"{SITE}/haber/1", allowed_hosts={"robots.example.com"})


def test_the_override_fetches_disallowed_urls_and_warns_once_per_host(
    make_http: Callable[..., Http], requests_mock: Mocker, caplog: pytest.LogCaptureFixture
) -> None:
    requests_mock.get(f"{SITE}/robots.txt", content=b"User-agent: *\nDisallow: /\n")
    requests_mock.get(f"{SITE}/private/page", text="ok")
    http = make_http(obey_robots=False)
    with caplog.at_level(logging.WARNING, logger="tr_news_scraper.http"):
        http.get(f"{SITE}/private/page", allowed_hosts={"robots.example.com"})
        http.get(f"{SITE}/private/page", allowed_hosts={"robots.example.com"})
    assert [r.path for r in requests_mock.request_history] == ["/private/page", "/private/page"]
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "robots.example.com" in warnings[0].getMessage()
