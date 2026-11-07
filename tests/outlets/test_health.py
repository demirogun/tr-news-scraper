"""Health checks: what the weekly live check calls a broken outlet."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest
from requests_mock import Mocker

from tr_news_scraper._http import Http
from tr_news_scraper.outlets import Month, MonthlySitemap, SiteSearch
from tr_news_scraper.outlets._health import check
from tr_news_scraper.outlets._search import page_url

BASE = "https://www.example.com.tr"
INDEX = f"{BASE}/sitemaps/posts.xml"
TODAY = date(2026, 11, 7)
LAST_MONTH = Month(2026, 10)
NS = 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'
IMAGE_NS = 'xmlns:image="http://www.google.com/schemas/sitemap-image/1.1"'
SITEMAP = MonthlySitemap(
    id="ornek",
    name="Örnek",
    index=INDEX,
    month_file=r"/sitemaps/posts-(?P<year>\d{4})-(?P<month>\d{2})\.xml$",
    earliest=Month(2010, 1),
)
WITH_TITLES = MonthlySitemap(
    id="ornek",
    name="Örnek",
    index=INDEX,
    month_file=r"/sitemaps/posts-(?P<year>\d{4})-(?P<month>\d{2})\.xml$",
    titles="image",
)
SEARCH = SiteSearch(
    id="ornek-arama",
    name="Örnek",
    url=f"{BASE}/api/search?query={{query}}&page={{page}}",
    item="//div[@class='news__item']",
    link=".//a/@href",
    title=".//a",
    date=".//span",
    date_format="%d.%m.%Y",
)


def file_url(month: Month) -> str:
    return f"{BASE}/sitemaps/posts-{month}.xml"


def index_of(*months: Month) -> str:
    entries = "".join(f"<sitemap><loc>{file_url(month)}</loc></sitemap>" for month in months)
    return f'<?xml version="1.0"?><sitemapindex {NS}>{entries}</sitemapindex>'


def urls(*locs: str, titles: bool = False) -> str:
    image = "<image:image><image:title>Başlık</image:title></image:image>" if titles else ""
    entries = "".join(f"<url><loc>{loc}</loc>{image}</url>" for loc in locs)
    return f'<?xml version="1.0"?><urlset {NS} {IMAGE_NS}>{entries}</urlset>'


ARTICLES = [f"{BASE}/gundem/haber-{n}" for n in range(3)]


def serve_sitemaps(requests_mock: Mocker, *months: Month, last_month: str | None = None) -> None:
    requests_mock.get(INDEX, text=index_of(*months))
    requests_mock.get(file_url(LAST_MONTH), text=last_month or urls(*ARTICLES))


def test_a_healthy_sitemap_outlet_costs_two_requests(http: Http, requests_mock: Mocker) -> None:
    serve_sitemaps(requests_mock, Month(2010, 1), LAST_MONTH, Month(2026, 11))
    health = check(SITEMAP, http, today=TODAY)
    assert health.ok, health.problems
    assert (health.oldest, health.newest, health.sample) == (
        Month(2010, 1),
        Month(2026, 11),
        3,
    )
    archive = [r.url for r in requests_mock.request_history if not r.url.endswith("robots.txt")]
    assert archive == [INDEX, file_url(LAST_MONTH)]


def test_a_health_check_reads_fresh_files_not_the_cache(http: Http, requests_mock: Mocker) -> None:
    serve_sitemaps(requests_mock, Month(2010, 1), LAST_MONTH)
    check(SITEMAP, http, today=TODAY)
    check(SITEMAP, http, today=TODAY)
    archive = [r.url for r in requests_mock.request_history if not r.url.endswith("robots.txt")]
    assert len(archive) == 4


@pytest.mark.parametrize(
    ("index", "problem"),
    [
        ({"status_code": 404}, "its sitemap index couldn't be read: the request failed"),
        (
            {
                "text": f'<?xml version="1.0"?><sitemapindex {NS}><sitemap><loc>{BASE}/feeds/pages'
                "</loc></sitemap></sitemapindex>"
            },
            "no entry in its sitemap index matches month_file",
        ),
    ],
)
def test_an_unreadable_or_unrecognizable_index_is_a_problem(
    http: Http, requests_mock: Mocker, index: dict[str, Any], problem: str
) -> None:
    requests_mock.get(INDEX, **index)
    health = check(SITEMAP, http, today=TODAY)
    assert not health.ok
    assert health.problems[0].startswith(problem)


def test_an_index_that_stopped_updating_is_a_problem(http: Http, requests_mock: Mocker) -> None:
    serve_sitemaps(requests_mock, Month(2010, 1), Month(2026, 8))
    assert check(SITEMAP, http, today=TODAY).problems == (
        "its index ends in 2026-08, so the archive seems to have stopped",
        "its index doesn't list last month (2026-10)",
    )


def test_an_index_that_lost_its_oldest_months_is_a_problem(
    http: Http, requests_mock: Mocker
) -> None:
    serve_sitemaps(requests_mock, Month(2015, 3), LAST_MONTH)
    assert check(SITEMAP, http, today=TODAY).problems == (
        "its index now starts in 2015-03, after the declared 2010-01",
    )


@pytest.mark.parametrize(
    ("last_month", "problem"),
    [
        (urls(), "the file for 2026-10 is empty"),
        (
            urls(*ARTICLES[:2], "http://www.example.com.tr/gundem/haber-9"),
            "1 of 3 entries in the file for 2026-10 aren't HTTPS URLs on its hosts",
        ),
        ("<urlset><url>", "the file for 2026-10 couldn't be read: it isn't well-formed XML"),
    ],
)
def test_a_bad_file_for_last_month_is_a_problem(
    http: Http, requests_mock: Mocker, last_month: str, problem: str
) -> None:
    serve_sitemaps(requests_mock, Month(2010, 1), LAST_MONTH, last_month=last_month)
    assert check(SITEMAP, http, today=TODAY).problems == (problem,)


def test_headlines_that_disappear_are_a_problem(http: Http, requests_mock: Mocker) -> None:
    serve_sitemaps(requests_mock, LAST_MONTH, last_month=urls(*ARTICLES))
    assert check(WITH_TITLES, http, today=TODAY).problems == (
        "only 0 of 3 entries in the file for 2026-10 have a headline",
    )
    serve_sitemaps(requests_mock, LAST_MONTH, last_month=urls(*ARTICLES, titles=True))
    assert check(WITH_TITLES, http, today=TODAY).ok


def result(link: str, day: date, title: str = "Başlık") -> str:
    return (
        f'<div class="news__item"><a href="{link}">{title}</a>'
        f"<span>{day.day}.{day.month}.{day.year}</span></div>"
    )


def results_page(first_day: date, count: int = 25, *, step: int = 0, title: str = "Başlık") -> str:
    return "".join(
        result(f"{BASE}/gundem/haber-{first_day}-{n}", first_day - timedelta(days=n * step), title)
        for n in range(count)
    )


def serve_search(requests_mock: Mocker, page_1: str, page_2: str) -> None:
    requests_mock.get(page_url(SEARCH, "deprem", 1), text=page_1)
    requests_mock.get(page_url(SEARCH, "deprem", 2), text=page_2)


def test_a_healthy_search_outlet_costs_two_requests(http: Http, requests_mock: Mocker) -> None:
    serve_search(requests_mock, results_page(TODAY), results_page(TODAY - timedelta(days=1)))
    health = check(SEARCH, http, today=TODAY)
    assert health.ok, health.problems
    assert health.sample == 25
    searches = [r.url for r in requests_mock.request_history if "/api/search" in r.url]
    assert searches == [page_url(SEARCH, "deprem", 1), page_url(SEARCH, "deprem", 2)]


def test_too_few_complete_results_are_a_problem(http: Http, requests_mock: Mocker) -> None:
    serve_search(
        requests_mock,
        results_page(TODAY, 5) + results_page(TODAY, 20, title=""),
        results_page(TODAY - timedelta(days=1)),
    )
    assert check(SEARCH, http, today=TODAY).problems == (
        "page 1 for 'deprem' has 5 complete results; at least 10 were expected",
    )


def test_results_out_of_order_are_a_problem(http: Http, requests_mock: Mocker) -> None:
    older_first = result(f"{BASE}/a-1", TODAY - timedelta(days=3)) + results_page(TODAY, 12)
    serve_search(requests_mock, older_first, results_page(TODAY))
    assert check(SEARCH, http, today=TODAY).problems == (
        "the dates on page 1 aren't newest first",
        "page 2 has results newer than page 1's",
    )


def test_a_search_with_nothing_recent_is_a_problem(http: Http, requests_mock: Mocker) -> None:
    stale = TODAY - timedelta(days=30)
    serve_search(requests_mock, results_page(stale), results_page(stale - timedelta(days=1)))
    assert check(SEARCH, http, today=TODAY).problems == (
        f"its newest result is from {stale}, more than 14 days ago",
    )


def test_a_search_page_that_fails_is_a_problem(http: Http, requests_mock: Mocker) -> None:
    requests_mock.get(page_url(SEARCH, "deprem", 1), status_code=403)
    assert check(SEARCH, http, today=TODAY).problems == (
        "page 1 couldn't be read: the site refused it with HTTP 403",
    )
