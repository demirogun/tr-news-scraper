"""search() and coverage() take chunked sitemaps like the other kinds of outlet."""

from __future__ import annotations

from datetime import datetime, timedelta

from requests_mock import Mocker

from tr_news_scraper import coverage
from tr_news_scraper._http import Http
from tr_news_scraper._search import _search
from tr_news_scraper.outlets import ChunkedSitemap, Month
from tr_news_scraper.outlets._dates import ISTANBUL

BASE = "https://www.example.com.tr"
NS = 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'
NOW = datetime(2026, 11, 7, 12, 0, tzinfo=ISTANBUL)
OUTLET = ChunkedSitemap(
    id="ornek-arsiv",
    name="Örnek Arşiv",
    index=f"{BASE}/sitemap.xml",
    chunk_file=r"/post-sitemap(?P<n>\d*)\.xml$",
    chunk_order="newest-first",
    entry_order="newest-first",
    earliest=Month(2023, 1),
    notes="Numbered files, newest first.",
)


def serve(requests_mock: Mocker) -> None:
    """Three files of 40 articles, one every 18 hours from 2023-01-01, numbered newest first."""
    first = datetime(2023, 1, 1, tzinfo=ISTANBUL)
    articles = [(k, first + k * timedelta(hours=18)) for k in range(120)]
    files = [articles[80:], articles[40:80], articles[:40]]
    locs = [f"{BASE}/post-sitemap.xml", f"{BASE}/post-sitemap2.xml", f"{BASE}/post-sitemap3.xml"]
    index = "".join(f"<sitemap><loc>{loc}</loc></sitemap>" for loc in locs)
    requests_mock.get(
        OUTLET.index, text=f'<?xml version="1.0"?><sitemapindex {NS}>{index}</sitemapindex>'
    )
    for loc, chunk in zip(locs, files, strict=True):
        urls = "".join(
            f"<url><loc>{BASE}/gundem/{'deprem' if k % 2 else 'spor'}-{k}</loc>"
            f"<lastmod>{when.isoformat()}</lastmod></url>"
            for k, when in reversed(chunk)
        )
        requests_mock.get(loc, text=f'<?xml version="1.0"?><urlset {NS}>{urls}</urlset>')


def test_search_reads_a_chunked_sitemap(http: Http, requests_mock: Mocker) -> None:
    requests_mock.get(f"{BASE}/robots.txt", status_code=404)
    serve(requests_mock)
    result = _search(
        ["deprem"], "2023-02-01", "2023-03-01", outlets=[OUTLET], http=http, now=NOW, offline=False
    )
    articles = result.articles
    assert len(articles) > 0
    assert set(articles["outlet"]) == {"ornek-arsiv"}
    assert set(articles["month"]) == {"2023-02"}
    assert all("deprem" in url for url in articles["url"])
    [row] = result.report.to_dict("records")
    assert row["outlet"] == "ornek-arsiv"


def test_coverage_describes_a_chunked_sitemap() -> None:
    [row] = coverage([OUTLET]).to_dict("records")
    assert (row["method"], row["earliest"], row["headlines"], row["notes"]) == (
        "chunked sitemap",
        "2023-01",
        "no",
        "Numbered files, newest first.",
    )
