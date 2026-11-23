"""The outlets tr-news-scraper knows, each checked live before it was added.

Each outlet's archive is allowed by its robots.txt. Most are read by default; opt-in outlets
are read only when named. A weekly live check (tests/live) confirms that every one still works.
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


# Sabah, A Haber, Takvim and Yeni Asır share Turkuvaz Medya's layout: one file a month, or
# several parts for a busy month (2023-2.xml, 2023-2-1.xml, ...).
_TURKUVAZ_MONTHS = r"/sitemaparchives/post/(?P<year>\d{4})-(?P<month>\d{1,2})(?:-\d+)?\.xml$"


A_HABER = MonthlySitemap(
    id="a-haber",
    name="A Haber",
    index="https://www.ahaber.com.tr/sitemap/post.xml",
    month_file=_TURKUVAZ_MONTHS,
    earliest=Month(2011, 3),
    notes="Every month since March 2011. No headlines.",
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

BUILTIN: tuple[Outlet, ...] = (
    CUMHURIYET,
    EURONEWS_TR,
    TRT_HABER,
    STAR,
    AKSAM,
    SOZCU,
    MILLIYET,
    A_HABER,
)
"""The default outlets: search reads them unless told otherwise."""
OPT_IN: tuple[Outlet, ...] = ()
"""Built-in outlets read only when named, so nobody gets them by surprise."""


def builtin(*, include_opt_in: bool = False) -> tuple[Outlet, ...]:
    """The outlets search uses by default, in a fixed order; with ``include_opt_in=True``,
    every built-in outlet: the defaults, then the opt-in ones.

    >>> builtin()                       # the defaults
    >>> builtin(include_opt_in=True)    # every built-in outlet
    """
    return (*BUILTIN, *OPT_IN) if include_opt_in else BUILTIN


def get(outlet_id: str) -> Outlet:
    """The built-in outlet with this id, opt-in ones included. Raises ``ValueError`` naming the
    valid ids."""
    every = builtin(include_opt_in=True)
    for outlet in every:
        if outlet.id == outlet_id:
            return outlet
    choices = ", ".join(outlet.id for outlet in every)
    raise ValueError(f"there's no built-in outlet {outlet_id!r}; choose from {choices}")
