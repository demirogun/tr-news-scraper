"""The outlets tr-news-scraper reads by default, each checked live on 2026-11-07.

Each outlet's archive is allowed by its robots.txt. A weekly live check (tests/live) confirms
that every one still works.
"""

from __future__ import annotations

from tr_news_scraper.outlets._model import Month, MonthlySitemap, Outlet

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

BUILTIN: tuple[Outlet, ...] = (CUMHURIYET, EURONEWS_TR, TRT_HABER, STAR, AKSAM, SOZCU)


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
