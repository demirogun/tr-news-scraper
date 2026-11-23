"""Milliyet's site search, as tr-news-scraper 1.0 read it: the tests' site-search outlet.

Milliyet was a built-in outlet until 2026-11-23, when its robots.txt began to disallow /api/ for
every crawler, its search included. Its search pages, recorded on 2026-11-07 while robots.txt
allowed them (tests/outlets/fixtures/milliyet), still test the kind end to end. No test sends a
request.
"""

from __future__ import annotations

from tr_news_scraper.outlets import SiteSearch


def _has_class(name: str) -> str:
    """An XPath test for an element whose class list includes ``name``."""
    return f"contains(concat(' ', normalize-space(@class), ' '), ' {name} ')"


MILLIYET = SiteSearch(
    id="milliyet",
    name="Milliyet",
    url="https://www.milliyet.com.tr/api/search/searchcontentloadmore?query={query}&page={page}",
    item=f"//div[{_has_class('news__item')}]",
    link=f".//a[{_has_class('news__titles-link')}]/@href",
    title=f".//strong[{_has_class('news__title')}]",
    date=f".//span[{_has_class('news__date')}]",
    date_format="%d.%m.%Y",
    # Links to /uzmanpara/ redirect to this section host.
    extra_hosts=frozenset({"uzmanpara.milliyet.com.tr"}),
    notes=(
        "Milliyet's search returns only its newest 10,000 results for each keyword; for a "
        "frequent word like 'deprem' that reaches back about two and a half years."
    ),
)
