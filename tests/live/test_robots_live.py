"""Live check (weekly CI only): robots.txt still allows what 1.0 reads, and still forbids what it
must not.

Run with ``uv run pytest -m live tests/live --no-cov``. These tests talk to real news sites, with
robots.txt obeyed and the honest User-Agent, so they never run in the normal test suite. A failure
means an outlet changed its rules: the outlet has to change too.
"""

from __future__ import annotations

import pytest

from tr_news_scraper._http import Http

# URLs that 1.0 reads, one per outlet; allowed by each site's robots.txt (checked 2026-11-07).
ALLOWED = {
    "Cumhuriyet": "https://www.cumhuriyet.com.tr/sitemaps/posts-2023-2.xml",
    "Euronews Türkçe": "https://tr.euronews.com/sitemap/articles-2023-02.xml",
    "TRT Haber": "https://www.trthaber.com/sitemaps/news-2023-02.xml",
    "Star": "https://www.star.com.tr/sitemaps/posts-2023-02.xml",
    "Akşam": "https://www.aksam.com.tr/sitemaps/posts-2023-02.xml",
    "Sözcü": "https://www.sozcu.com.tr/feeds/sitemapposts?year=2024&month=6",
    "Milliyet": "https://www.milliyet.com.tr/api/search/searchcontentloadmore?query=deprem&page=1",
    "Milliyet Uzmanpara": (
        "https://uzmanpara.milliyet.com.tr/uzmanpara/"
        "deprem-tarlasini-ikiye-bolmustu-ucurum-kenarinda-hasat-yapiyorlar-7692430"
    ),
}
# Endpoints that 0.1.0 used, or that we once planned to use, and that robots.txt now forbids.
DISALLOWED = {
    "Sabah search": "https://www.sabah.com.tr/get/arama?query=deprem",
    "Hürriyet search": "https://www.hurriyet.com.tr/api/search/searchcontentloadmore?query=deprem",
    "CNN Türk tag list (disallowed since 2026-11-07)": (
        "https://www.cnnturk.com/api/lazy/loadmore?tags=deprem&skip=0&top=10"
    ),
}


@pytest.fixture(scope="module")
def http() -> Http:
    return Http()


@pytest.mark.live
@pytest.mark.parametrize("url", ALLOWED.values(), ids=ALLOWED.keys())
def test_robots_txt_allows_the_urls_we_read(http: Http, url: str) -> None:
    assert http._robots.allows(url)


@pytest.mark.live
@pytest.mark.parametrize("url", DISALLOWED.values(), ids=DISALLOWED.keys())
def test_endpoints_we_must_not_use_are_still_disallowed(http: Http, url: str) -> None:
    assert not http._robots.allows(url)
