"""The outlets tr-news-scraper reads by default, each checked live on 2026-11-07.

Each outlet's archive is allowed by its robots.txt. A weekly live check (tests/live) confirms
that every one still works.
"""

from __future__ import annotations

from tr_news_scraper.outlets._model import Month, MonthlySitemap, Outlet, SiteSearch

CUMHURIYET = MonthlySitemap(
    id="cumhuriyet",
    name="Cumhuriyet",
    index="https://www.cumhuriyet.com.tr/sitemaps/posts.xml",
    month_file=r"/sitemaps/posts-(?P<year>\d{4})-(?P<month>\d{1,2})\.xml$",
    earliest=Month(1962, 8),
    notes="Every month since July 2008; only scattered months before. No headlines.",
)

EURONEWS_TR = MonthlySitemap(
    id="euronews-tr",
    name="Euronews Türkçe",
    index="https://tr.euronews.com/sitemap/articles.xml",
    month_file=r"/sitemap/articles-(?P<year>\d{4})-(?P<month>\d{2})\.xml$",
    earliest=Month(2010, 1),
    notes="Matched on URLs only: the titles in its sitemaps describe photos, not articles.",
)

TRT_HABER = MonthlySitemap(
    id="trt-haber",
    name="TRT Haber",
    index="https://www.trthaber.com/sitemaps/news.xml",
    month_file=r"/sitemaps/news-(?P<year>\d{4})-(?P<month>\d{2})\.xml$",
    earliest=Month(2016, 7),
    notes="Lists article URLs without headlines.",
)

STAR = MonthlySitemap(
    id="star",
    name="Star",
    index="https://www.star.com.tr/sitemaps/posts.xml",
    month_file=r"/sitemaps/posts-(?P<year>\d{4})-(?P<month>\d{2})\.xml$",
    titles="image",
    earliest=Month(2012, 9),
    notes="Headlines come from the image titles in its sitemaps.",
)

AKSAM = MonthlySitemap(
    id="aksam",
    name="Akşam",
    index="https://www.aksam.com.tr/sitemaps/posts.xml",
    month_file=r"/sitemaps/posts-(?P<year>\d{4})-(?P<month>\d{2})\.xml$",
    earliest=Month(2010, 12),
    notes="Lists article URLs without headlines.",
)

SOZCU = MonthlySitemap(
    id="sozcu",
    name="Sözcü",
    index="https://www.sozcu.com.tr/feeds/sitemapindex",
    month_file=r"/feeds/sitemapposts\?year=(?P<year>\d{4})&month=(?P<month>\d{1,2})$",
    earliest=Month(2023, 12),
    notes="Sözcü's new website, from December 2023; older articles aren't in its archive.",
)


def _has_class(name: str) -> str:
    """An XPath test for an element whose class list includes ``name``."""
    return f"contains(concat(' ', normalize-space(@class), ' '), ' {name} ')"


# /api/search/ is allowed by Milliyet's robots.txt; its /arama/ pages are not, and aren't used.
MILLIYET = SiteSearch(
    id="milliyet",
    name="Milliyet",
    url="https://www.milliyet.com.tr/api/search/searchcontentloadmore?query={query}&page={page}",
    item=f"//div[{_has_class('news__item')}]",
    link=f".//a[{_has_class('news__titles-link')}]/@href",
    title=f".//strong[{_has_class('news__title')}]",
    date=f".//span[{_has_class('news__date')}]",
    date_format="%d.%m.%Y",
    # Links to /uzmanpara/ redirect to this section host, whose robots.txt allows articles.
    extra_hosts=frozenset({"uzmanpara.milliyet.com.tr"}),
    notes=(
        "Milliyet's search returns only its newest 10,000 results for each keyword; for a "
        "frequent word like 'deprem' that reaches back about two and a half years."
    ),
)

BUILTIN: tuple[Outlet, ...] = (CUMHURIYET, EURONEWS_TR, TRT_HABER, STAR, AKSAM, SOZCU, MILLIYET)


def builtin() -> tuple[Outlet, ...]:
    """The outlets search uses by default, in a fixed order."""
    return BUILTIN


def get(outlet_id: str) -> Outlet:
    """The built-in outlet with this id. Raises ``ValueError`` naming the valid ids."""
    for outlet in BUILTIN:
        if outlet.id == outlet_id:
            return outlet
    choices = ", ".join(outlet.id for outlet in BUILTIN)
    raise ValueError(f"there's no built-in outlet {outlet_id!r}; choose from {choices}")
