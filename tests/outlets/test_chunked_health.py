"""The health check of a chunked sitemap (K7): three requests, and every problem it names."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import pytest
from requests_mock import Mocker

from tr_news_scraper._http import Http
from tr_news_scraper.outlets import ChunkedSitemap, Month
from tr_news_scraper.outlets._dates import ISTANBUL
from tr_news_scraper.outlets._health import check

BASE = "https://www.example.com.tr"
INDEX = f"{BASE}/story-sitemap"
NS = 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'
NEWS_NS = 'xmlns:news="http://www.google.com/schemas/sitemap-news/0.9"'
TODAY = date(2026, 11, 7)
OUTLET: dict[str, Any] = {
    "id": "ornek",
    "name": "Örnek",
    "index": INDEX,
    "chunk_file": r"/story-sitemap/(?P<n>\d+)$",
    "chunk_order": "oldest-first",
    "entry_order": "newest-first",
    "earliest": Month(2008, 12),
}


def outlet(**changes: Any) -> ChunkedSitemap:
    return ChunkedSitemap(**(OUTLET | changes))


def chunk_url(n: int) -> str:
    return f"{BASE}/story-sitemap/{n}"


def entries(newest: datetime, count: int = 10, *, title: str | None = None, step: int = 1) -> str:
    """``count`` entries, newest first, one hour apart (``step`` hours)."""
    parts = []
    for k in range(count):
        when = (newest - timedelta(hours=k * step)).isoformat()
        news = "" if title is None else f"<news:news><news:title>{title}</news:title></news:news>"
        parts.append(f"<url><loc>{BASE}/haber/{k}</loc><lastmod>{when}</lastmod>{news}</url>")
    return f'<?xml version="1.0"?><urlset {NS} {NEWS_NS}>{"".join(parts)}</urlset>'


RECENT = datetime(2026, 11, 6, 18, 0, tzinfo=ISTANBUL)
OLD = datetime(2008, 12, 20, 12, 0, tzinfo=ISTANBUL)


def serve(requests_mock: Mocker, *, newest: str | None = None, oldest: str | None = None) -> None:
    index = "".join(f"<sitemap><loc>{chunk_url(n)}</loc></sitemap>" for n in range(1, 6))
    requests_mock.get(INDEX, text=f'<?xml version="1.0"?><sitemapindex {NS}>{index}</sitemapindex>')
    requests_mock.get(chunk_url(5), text=newest or entries(RECENT))
    requests_mock.get(chunk_url(1), text=oldest or entries(OLD))


def archive_requests(requests_mock: Mocker) -> list[str]:
    return [r.url for r in requests_mock.request_history if not r.url.endswith("robots.txt")]


def test_a_healthy_chunked_archive_costs_three_requests(http: Http, requests_mock: Mocker) -> None:
    serve(requests_mock)
    health = check(outlet(), http, today=TODAY)
    assert health.ok, health.problems
    assert (health.oldest, health.newest, health.sample) == (Month(2008, 12), Month(2026, 11), 10)
    assert archive_requests(requests_mock) == [INDEX, chunk_url(5), chunk_url(1)]


@pytest.mark.parametrize(
    ("changes", "newest", "problem"),
    [
        ({}, entries(RECENT, 0), "its newest file is empty"),
        (
            {},
            entries(datetime(2026, 10, 1, tzinfo=ISTANBUL)),
            "its newest file's newest date is 2026-10-01, more than 14 days ago",
        ),
        (
            {"entry_order": "oldest-first"},
            entries(RECENT, 40),
            "its newest file's dates don't follow entry_order (oldest-first): only 0 of 9",
        ),
        ({"titles": "news"}, None, "only 0 of 10 entries in its newest file have a headline"),
        (
            {},
            entries(RECENT).replace(f"{BASE}/haber/3<", "http://www.example.com.tr/haber/3<"),
            "1 of 10 entries in its newest file aren't HTTPS URLs on its hosts",
        ),
        (
            {},
            entries(RECENT).replace("2026-11-06", "garbage").replace("2026-11-05", "garbage"),
            "its newest file has no dates",
        ),
    ],
    ids=["empty", "stale", "out-of-order", "no-headlines", "off-host", "undated"],
)
def test_each_problem_with_the_newest_file_is_named(
    http: Http, requests_mock: Mocker, changes: dict[str, Any], newest: str | None, problem: str
) -> None:
    serve(requests_mock, newest=newest)
    health = check(outlet(**changes), http, today=TODAY)
    assert any(found.startswith(problem) for found in health.problems), health.problems


def test_news_titles_in_the_newest_file_count_as_headlines(
    http: Http, requests_mock: Mocker
) -> None:
    serve(requests_mock, newest=entries(RECENT, title="Başlık"))
    assert check(outlet(titles="news"), http, today=TODAY).ok


def test_an_oldest_file_long_after_the_declared_earliest_month_is_a_problem(
    http: Http, requests_mock: Mocker
) -> None:
    serve(requests_mock, oldest=entries(datetime(2009, 3, 10, tzinfo=ISTANBUL)))
    health = check(outlet(), http, today=TODAY)
    assert health.problems == (
        "its oldest file is dated 2009-03, more than a month after the declared 2008-12",
    )


@pytest.mark.parametrize(
    ("broken", "problem"),
    [
        (INDEX, "its sitemap index couldn't be read: the request failed (HTTP 404, 1 attempt)"),
        (
            chunk_url(5),
            "its newest file couldn't be read: the request failed (HTTP 404, 1 attempt)",
        ),
        (
            chunk_url(1),
            "its oldest file couldn't be read: the request failed (HTTP 404, 1 attempt)",
        ),
    ],
)
def test_a_file_that_cant_be_read_is_a_problem(
    http: Http, requests_mock: Mocker, broken: str, problem: str
) -> None:
    serve(requests_mock)
    requests_mock.get(broken, status_code=404)
    assert problem in check(outlet(), http, today=TODAY).problems


def test_an_index_without_numbered_files_is_a_problem(http: Http, requests_mock: Mocker) -> None:
    requests_mock.get(INDEX, text=f'<?xml version="1.0"?><sitemapindex {NS}></sitemapindex>')
    health = check(outlet(), http, today=TODAY)
    assert health.problems == ("no entry in its sitemap index matches chunk_file",)


def test_an_archive_of_one_file_reads_it_once(http: Http, requests_mock: Mocker) -> None:
    index = f"<sitemap><loc>{chunk_url(1)}</loc></sitemap>"
    requests_mock.get(INDEX, text=f'<?xml version="1.0"?><sitemapindex {NS}>{index}</sitemapindex>')
    requests_mock.get(chunk_url(1), text=entries(RECENT))
    health = check(outlet(earliest=Month(2026, 11)), http, today=TODAY)
    assert health.ok, health.problems
    assert archive_requests(requests_mock) == [INDEX, chunk_url(1)]


def test_an_undated_oldest_file_gives_no_oldest_month(http: Http, requests_mock: Mocker) -> None:
    undated = f'<?xml version="1.0"?><urlset {NS}><url><loc>{BASE}/haber/1</loc></url></urlset>'
    serve(requests_mock, oldest=undated)
    health = check(outlet(), http, today=TODAY)
    assert health.ok, health.problems
    assert health.oldest is None


def test_later_edits_dont_upset_the_order_check(http: Http, requests_mock: Mocker) -> None:
    # A quarter of the entries edited later, out of place among their neighbours.
    body = entries(RECENT, 80)
    for k in range(0, 80, 4):
        stamp = (RECENT - timedelta(hours=k)).isoformat()
        body = body.replace(
            f"<lastmod>{stamp}</lastmod>", f"<lastmod>{RECENT.isoformat()}</lastmod>", 1
        )
    serve(requests_mock, newest=body)
    health = check(outlet(), http, today=TODAY)
    assert health.ok, health.problems


def test_a_newest_file_too_small_to_judge_its_order_isnt_judged(
    http: Http, requests_mock: Mocker
) -> None:
    serve(requests_mock, newest=entries(RECENT, 12))
    assert check(outlet(entry_order="oldest-first"), http, today=TODAY).ok


def test_the_oldest_month_is_its_first_articles_not_its_median(
    http: Http, requests_mock: Mocker
) -> None:
    # A big oldest file: its median is months after its first article.
    big = entries(datetime(2009, 6, 1, tzinfo=ISTANBUL), 60, step=24 * 5)
    serve(requests_mock, oldest=big)
    health = check(outlet(earliest=Month(2008, 12)), http, today=TODAY)
    assert health.ok, health.problems
    assert health.oldest == Month(2008, 12)
