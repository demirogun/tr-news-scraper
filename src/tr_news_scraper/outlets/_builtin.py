"""The outlets tr-news-scraper knows, each checked live before it was added.

Each outlet's archive is allowed by its robots.txt. Most are read by default; opt-in outlets
are read only when named. A weekly live check (tests/live) confirms that every one still works.
"""

from __future__ import annotations

from tr_news_scraper.outlets._model import (
    ChunkedSitemap,
    Month,
    MonthlySitemap,
    Outlet,
    SiteSearch,
)

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


AYDINLIK = MonthlySitemap(
    id="aydinlik",
    name="Aydınlık",
    index="https://www.aydinlik.com.tr/sitemap/index",
    month_file=r"/sitemap/(?P<year>\d{4})/(?P<month>\d{1,2})$",
    earliest=Month(2010, 2),
    notes="Every month since April 2011; only scattered months before. No headlines.",
)


BLOOMBERG_HT = ChunkedSitemap(
    id="bloomberg-ht",
    name="Bloomberg HT",
    index="https://www.bloomberght.com/sitemap.xml",
    chunk_file=r"/sitemap_news_(?P<n>\d+)\.xml$",
    chunk_order="oldest-first",
    entry_order="newest-first",
    earliest=Month(2010, 9),
    notes="Numbered files of 1,000 articles each, back to September 2010. No headlines.",
)


DIKEN = ChunkedSitemap(
    id="diken",
    name="Diken",
    index="https://www.diken.com.tr/sitemap.xml",
    chunk_file=r"/post-sitemap(?P<n>\d*)\.xml$",
    chunk_order="newest-first",
    entry_order="newest-first",
    earliest=Month(2013, 12),
    notes=(
        "Numbered files of 1,000 articles each, the newest first, back to December 2013. "
        "No headlines."
    ),
)


EVRENSEL = ChunkedSitemap(
    id="evrensel",
    name="Evrensel",
    index="https://www.evrensel.net/sitemap.xml",
    chunk_file=r"/sitemap/haber/(?P<n>\d+)\.xml$",
    chunk_order="oldest-first",
    entry_order="newest-first",
    earliest=Month(2011, 2),
    notes="Numbered files of 10,000 articles each, back to February 2011. No headlines.",
)


HABER_GLOBAL = MonthlySitemap(
    id="haber-global",
    name="Haber Global",
    index="https://haberglobal.com/sitemap.xml",
    month_file=r"/sitemap-articles-(?P<year>\d{4})-(?P<month>\d{2})(?:-\d+)?\.xml$",
    earliest=Month(2019, 2),
    notes="Every month since February 2019, the busiest in two parts. No headlines.",
)


HABERTURK = MonthlySitemap(
    id="haberturk",
    name="Habertürk",
    index="https://www.haberturk.com/sitemap_posts.xml",
    month_file=r"/sitemap_post_(?P<year>\d{4})(?P<month>\d{2})\.xml$",
    grouping="last-edit",
    article_id=r"-(?P<id>\d{6,})(?:-[a-z]+)?$",
    earliest=Month(2006, 9),
    notes=(
        "Every month since September 2006. A month's file lists the articles last edited that "
        "month, so a scan also reads the month after and keeps its articles by number. "
        "No headlines."
    ),
)


KISA_DALGA = ChunkedSitemap(
    id="kisa-dalga",
    name="Kısa Dalga",
    index="https://kisadalga.net/sitemap.xsd",
    chunk_file=r"/sitemap-news-(?P<n>\d+)\.xml$",
    chunk_order="oldest-first",
    entry_order="oldest-first",
    earliest=Month(2020, 6),
    notes="Four large files of up to 40,000 articles each, back to June 2020. No headlines.",
)


MYNET = MonthlySitemap(
    id="mynet",
    name="Mynet",
    index="https://www.mynet.com/sitemaps/all-index.xml",
    month_file=r"/sitemaps/monthly/[^/]+/(?P<year>\d{4})-(?P<month>\d{2})(?:-p\d+)?\.xml$",
    extra_hosts=frozenset({"finans.mynet.com"}),
    earliest=Month(2013, 3),
    notes=(
        "A portal that carries much agency copy, in one file per section and month: every "
        "month since August 2014, scattered months before. No headlines."
    ),
)


NTV = ChunkedSitemap(
    id="ntv",
    name="NTV",
    index="https://www.ntv.com.tr/story-sitemap",
    chunk_file=r"/story-sitemap/(?P<n>\d+)$",
    chunk_order="oldest-first",
    entry_order="newest-first",
    earliest=Month(2008, 12),
    notes="Numbered files of about 1,000 articles each, back to December 2008. No headlines.",
)


ODATV = MonthlySitemap(
    id="odatv",
    name="Odatv",
    index="https://www.odatv.com/categories.xml",
    month_file=r"/[a-z0-9-]+/(?P<year>\d{4})-(?P<month>\d{2})\.xml$",
    titles="news",
    earliest=Month(2007, 9),
    notes=(
        "One file per section and month, every month since September 2007. Headlines and "
        "publication days come from its Google News tags."
    ),
)


OLAY = ChunkedSitemap(
    id="olay",
    name="Olay",
    index="https://www.olay.com.tr/sitemap_index.xml",
    chunk_file=r"/post-sitemap(?P<n>\d*)\.xml$",
    chunk_order="newest-first",
    entry_order="newest-first",
    earliest=Month(2014, 9),
    notes=(
        "A regional paper of Bursa. Numbered files of about 1,000 articles each, the newest "
        "first, back to September 2014. No headlines."
    ),
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
    AYDINLIK,
    BLOOMBERG_HT,
    DIKEN,
    EVRENSEL,
    HABER_GLOBAL,
    HABERTURK,
    KISA_DALGA,
    MYNET,
    NTV,
    ODATV,
    OLAY,
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
