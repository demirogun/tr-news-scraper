"""Site search: reading result pages, and finding a past range's pages with few requests."""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from requests_mock import Mocker

from tr_news_scraper._http import Http
from tr_news_scraper.errors import OutletFailed
from tr_news_scraper.outlets import Month, SiteSearch
from tr_news_scraper.outlets._scan import scan
from tr_news_scraper.outlets._search import (
    Outcome,
    Page,
    Result,
    SearchPageError,
    page_url,
    parse_page,
    query_text,
    results_in_range,
)

BASE = "https://www.example.com.tr"
OUTLET = SiteSearch(
    id="ornek-arama",
    name="Örnek",
    url=f"{BASE}/api/search?query={{query}}&page={{page}}",
    item="//div[contains(concat(' ', normalize-space(@class), ' '), ' news__item ')]",
    link=".//a[contains(@class, 'news__titles-link')]/@href",
    title=".//strong[contains(@class, 'news__title')]",
    date=".//span[contains(@class, 'news__date')]",
    date_format="%d.%m.%Y",
    max_pages=1000,
)
NEWEST = date(2026, 11, 7)
PAGES = 400  # like Milliyet: 400 pages of 25, then empty pages
PER_PAGE = 25


def item(link: str, day: date | str, title: str = "Başlık") -> str:
    shown = day if isinstance(day, str) else f"{day.day}.{day.month}.{day.year}"
    return (
        '<div class="news__item col-md-12">'
        f'<a href="{link}" class="news__link"><img alt="x"/></a>'
        f'<a href="{link}" class="news__titles-link"><strong class="news__title">\n  {title}\n'
        f'</strong></a><span class="news__date">{shown}</span></div>'
    )


def page_html(*items: str) -> str:
    return '<input id="searchLoadMore" type="hidden" value="25" />' + "".join(items)


def day_of(number: int) -> date:
    """Each page of the fake site holds one day's results, the newest page first."""
    return NEWEST - timedelta(days=number - 1)


def fake_page(number: int, pages: int = PAGES) -> Page:
    url = page_url(OUTLET, "deprem", number)
    if number > pages:
        return Page(number, url)
    day = day_of(number)
    results = tuple(Result(f"{BASE}/gundem/p{number}-{i}", day, None, url) for i in range(PER_PAGE))
    return Page(number, url, results, (day,) * PER_PAGE, PER_PAGE)


class FakeSite:
    """A newest-first search that counts the pages asked for."""

    def __init__(self, pages: int = PAGES) -> None:
        self.pages = pages
        self.fetched: list[int] = []

    def fetch(self, number: int) -> Page:
        self.fetched.append(number)
        return fake_page(number, self.pages)


def run(
    site: FakeSite, start: date, end: date, max_pages: int = 1000
) -> tuple[list[Result], Outcome]:
    outcome = Outcome()
    return list(results_in_range(site.fetch, start, end, max_pages, outcome)), outcome


def test_query_text_drops_the_matching_operators() -> None:
    assert query_text('"sel"') == "sel"
    assert query_text("deprem*") == "deprem"
    assert query_text("  toprak   kayması ") == "toprak kayması"
    assert query_text('"') == '"'


def test_the_query_is_percent_encoded_in_the_page_url() -> None:
    assert page_url(OUTLET, "toprak kayması", 3) == (
        f"{BASE}/api/search?query=toprak%20kaymas%C4%B1&page=3"
    )
    assert page_url(OUTLET, "a&b=c", 1) == f"{BASE}/api/search?query=a%26b%3Dc&page=1"


def test_a_page_gives_its_results_in_order() -> None:
    html = page_html(
        item(f"{BASE}/gundem/son-depremler-7696134", "7.11.2026", "SON DEPREMLER  7 KASIM"),
        item("/dunya/kolombiyada-deprem-7693612", date(2026, 11, 3), "Kolombiya'da deprem"),
    )
    page = parse_page(html, OUTLET, 1, page_url(OUTLET, "deprem", 1))
    assert page.results == (
        Result(
            f"{BASE}/gundem/son-depremler-7696134",
            date(2026, 11, 7),
            "SON DEPREMLER 7 KASIM",
            page.url,
        ),
        Result(
            f"{BASE}/dunya/kolombiyada-deprem-7693612",
            date(2026, 11, 3),
            "Kolombiya'da deprem",
            page.url,
        ),
    )
    assert (page.items, page.newest, page.oldest) == (2, date(2026, 11, 7), date(2026, 11, 3))


def test_results_off_the_outlets_hosts_are_dropped_but_still_order_the_page() -> None:
    html = page_html(
        item("https://elsewhere.example/a-1", date(2026, 11, 7)),
        item("http://www.example.com.tr/a-2", date(2026, 11, 6)),
        item(f"{BASE}/a-3", date(2026, 11, 5)),
    )
    page = parse_page(html, OUTLET, 1, f"{BASE}/api/search?query=x&page=1")
    assert [result.url for result in page.results] == [f"{BASE}/a-3"]
    assert (page.dropped, page.newest) == (2, date(2026, 11, 7))


def test_results_without_a_link_or_date_are_counted_as_unreadable() -> None:
    html = page_html(
        '<div class="news__item"><span class="news__date">7.11.2026</span></div>',
        item(f"{BASE}/a-2", "dün"),
        item(f"{BASE}/a-3", date(2026, 11, 5)),
    )
    page = parse_page(html, OUTLET, 1, f"{BASE}/api/search?query=x&page=1")
    assert [result.url for result in page.results] == [f"{BASE}/a-3"]
    assert page.unreadable == 2


@pytest.mark.parametrize(
    "html", ["", "   \n", '<input id="searchLoadMore" type="hidden" value="0" />']
)
def test_a_page_without_results_is_empty(html: str) -> None:
    assert parse_page(html, OUTLET, 401, f"{BASE}/x").empty


def test_a_page_whose_dates_cant_be_read_is_an_error() -> None:
    html = page_html(item(f"{BASE}/a-1", "dün"), item(f"{BASE}/a-2", "bugün"))
    with pytest.raises(SearchPageError, match="no date on page 3 could be read"):
        parse_page(html, OUTLET, 3, f"{BASE}/x")


def test_a_range_300_pages_deep_takes_at_most_12_requests_to_reach() -> None:
    site = FakeSite()
    start, end = day_of(305) + timedelta(days=1), day_of(299) + timedelta(days=1)
    results, outcome = run(site, start, end)
    # Page 1 and the binary search, which ends on page 299, the range's first page; then
    # reading goes forward until page 305 passes the start.
    searching, reading = site.fetched[:-6], site.fetched[-6:]
    assert len(searching) <= 12
    assert 299 in searching
    assert reading == list(range(300, 306))
    assert {result.day for result in results} == {day_of(n) for n in range(299, 305)}
    assert len(results) == 6 * PER_PAGE
    assert not outcome.exhausted


def test_a_recent_range_is_read_from_page_1_without_searching() -> None:
    site = FakeSite()
    results, outcome = run(site, day_of(4), NEWEST + timedelta(days=1))
    assert site.fetched == [1, 2, 3, 4, 5]
    assert len(results) == 4 * PER_PAGE
    assert not outcome.exhausted


def test_a_range_newer_than_every_result_costs_one_request() -> None:
    site = FakeSite()
    results, _ = run(site, NEWEST + timedelta(days=1), NEWEST + timedelta(days=5))
    assert (results, site.fetched) == ([], [1])


def test_a_range_older_than_the_results_reports_how_far_they_reach() -> None:
    site = FakeSite()
    results, outcome = run(site, day_of(600), day_of(500))
    assert results == []
    assert outcome.exhausted
    assert outcome.oldest_seen == day_of(PAGES)
    assert len(site.fetched) <= 12


def test_a_range_across_the_end_of_the_results_keeps_what_it_reaches() -> None:
    site = FakeSite()
    results, outcome = run(site, day_of(450), day_of(390))
    assert {result.day for result in results} == {day_of(n) for n in range(391, PAGES + 1)}
    assert outcome.exhausted
    assert outcome.oldest_seen == day_of(PAGES)
    assert site.fetched[-1] == PAGES + 1


def test_max_pages_bounds_the_search() -> None:
    site = FakeSite()
    results, outcome = run(site, day_of(120), day_of(100), max_pages=50)
    assert results == []
    assert outcome.exhausted
    assert outcome.oldest_seen == day_of(50)
    assert max(site.fetched) == 50


def test_reading_stops_at_max_pages_inside_the_range() -> None:
    site = FakeSite()
    results, outcome = run(site, day_of(80), day_of(40), max_pages=50)
    assert {result.day for result in results} == {day_of(n) for n in range(41, 51)}
    assert outcome.exhausted
    assert max(site.fetched) == 50


def test_a_start_day_that_goes_on_to_the_next_page_is_read_to_its_end() -> None:
    # Results carry days, not times, so a page whose oldest result is on the start day can't
    # show that the day is over: the next page can hold more of it. Reading stops only below
    # the start. Stopping on the start day would drop these articles and still report "full".
    start, end = date(2023, 2, 1), date(2023, 3, 1)
    days = {
        1: [date(2023, 2, 2)] * 2 + [start] * 2,
        2: [start] * 3 + [date(2023, 1, 31)],
    }

    def fetch(number: int) -> Page:
        url = page_url(OUTLET, "deprem", number)
        on_page = days.get(number, [])
        results = tuple(
            Result(f"{BASE}/gundem/p{number}-{i}", day, None, url) for i, day in enumerate(on_page)
        )
        return Page(number, url, results, tuple(on_page), len(on_page))

    outcome = Outcome()
    results = list(results_in_range(fetch, start, end, 1000, outcome))
    assert [result.day for result in results].count(start) == 5
    assert outcome.pages == [1, 2]
    assert not outcome.exhausted


def test_an_empty_search_has_no_results() -> None:
    site = FakeSite(pages=0)
    results, outcome = run(site, day_of(10), day_of(1))
    assert (results, site.fetched, outcome.exhausted) == ([], [1], False)


# Scanning a site-search outlet through Http, with the fake site served by requests-mock.


def serve(requests_mock: Mocker, pages: int = PAGES, fail_page: int | None = None) -> None:
    def respond(request: Any, context: Any) -> str:
        number = int(parse_qs(urlsplit(request.url).query)["page"][0])
        if number == fail_page:
            context.status_code = 403
            return ""
        if number > pages:
            return '<input id="searchLoadMore" type="hidden" value="0" />'
        return page_html(
            *(item(f"{BASE}/gundem/p{number}-{i}", day_of(number)) for i in range(PER_PAGE))
        )

    requests_mock.get(re.compile(re.escape(f"{BASE}/api/search?")), text=respond)


def search_requests(requests_mock: Mocker) -> list[str]:
    return [r.url for r in requests_mock.request_history if "/api/search" in r.url]


def collect(found: Iterator[Any]) -> list[Any]:
    return list(found)


def test_a_scan_turns_results_into_dated_candidates(http: Http, requests_mock: Mocker) -> None:
    serve(requests_mock)
    found = scan(OUTLET, http, day_of(2), NEWEST + timedelta(days=1), ["deprem"], today=NEWEST)
    candidates = collect(iter(found))
    assert len(candidates) == 2 * PER_PAGE
    first = candidates[0]
    assert (first.outlet, first.day, first.month, first.title) == (
        "ornek-arama",
        NEWEST,
        Month(2026, 11),
        "Başlık",
    )
    assert first.source == page_url(OUTLET, "deprem", 1)
    assert found.gaps == []


def test_keywords_with_the_same_query_are_searched_once(http: Http, requests_mock: Mocker) -> None:
    serve(requests_mock)
    found = scan(
        OUTLET, http, day_of(1), NEWEST + timedelta(days=1), ["deprem", "deprem*"], today=NEWEST
    )
    collect(iter(found))
    assert search_requests(requests_mock) == [
        page_url(OUTLET, "deprem", 1),
        page_url(OUTLET, "deprem", 2),
    ]


def test_results_that_run_out_are_a_window_gap(http: Http, requests_mock: Mocker) -> None:
    serve(requests_mock, pages=30)
    found = scan(OUTLET, http, day_of(60), day_of(40), ["deprem"], today=NEWEST)
    assert collect(iter(found)) == []
    [gap] = found.gaps
    assert (gap.reason, gap.keyword) == ("window", "deprem")
    assert gap.detail == (
        f"Örnek's search has nothing older than {day_of(30)} for 'deprem', so the rest of the "
        "range can't be reached through it"
    )


def test_a_failed_page_stops_that_keyword_and_the_scan_goes_on(
    http: Http, requests_mock: Mocker
) -> None:
    serve(requests_mock, fail_page=2)
    found = scan(
        OUTLET, http, day_of(3), NEWEST + timedelta(days=1), ["deprem", "sel"], today=NEWEST
    )
    candidates = collect(iter(found))
    assert len(candidates) == 2 * PER_PAGE  # page 1 of each keyword
    assert [(gap.reason, gap.keyword) for gap in found.gaps] == [
        ("blocked", "deprem"),
        ("blocked", "sel"),
    ]
    assert found.gaps[0].url == page_url(OUTLET, "deprem", 2)


def test_an_outlet_whose_every_page_failed_fails(http: Http, requests_mock: Mocker) -> None:
    serve(requests_mock, fail_page=1)
    found = scan(OUTLET, http, day_of(3), NEWEST, ["deprem"], today=NEWEST)
    with pytest.raises(OutletFailed, match="none of the files it needed could be read"):
        collect(iter(found))


@pytest.mark.parametrize("keywords", [[], ['""', "*"]])
def test_no_searchable_keyword_means_no_requests(
    http: Http, requests_mock: Mocker, keywords: list[str]
) -> None:
    serve(requests_mock)
    found = scan(OUTLET, http, day_of(3), NEWEST, keywords, today=NEWEST)
    assert (collect(iter(found)), search_requests(requests_mock)) == ([], [])
