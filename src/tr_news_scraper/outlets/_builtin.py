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


OZGUR_KOCAELI = MonthlySitemap(
    id="ozgur-kocaeli",
    name="Özgür Kocaeli",
    index="https://www.ozgurkocaeli.com.tr/sitemap.xml",
    month_file=r"/sites/\d+/sitemaps/sitemap-(?P<year>\d{4})-(?P<month>\d{2})\.xml$",
    earliest=Month(2006, 1),
    notes=(
        "A regional paper of Kocaeli, the 1999 earthquake's area. Every month since September "
        "2010; only scattered months before. No headlines."
    ),
)


SABAH = MonthlySitemap(
    id="sabah",
    name="Sabah",
    index="https://www.sabah.com.tr/sitemap/post.xml",
    month_file=_TURKUVAZ_MONTHS,
    extra_hosts=frozenset({"finans.sabah.com.tr"}),
    earliest=Month(2003, 11),
    notes=(
        "Every month since November 2003, the busiest in parts; about 3% of its articles are "
        "on finans.sabah.com.tr. No headlines."
    ),
)


SPUTNIK_TR = MonthlySitemap(
    id="sputnik-tr",
    name="Sputnik Türkiye",
    index="https://anlatilaninotesi.com.tr/sitemap_article_index.xml",
    month_file=r"/sitemap_article\.xml\?date_start=(?P<year>\d{4})(?P<month>\d{2})01&",
    earliest=Month(2014, 11),
    notes=(
        "Opt-in: funded by the Russian state, so it's read only when you name it. Every month "
        "since November 2014. No headlines."
    ),
)


TAKVIM = MonthlySitemap(
    id="takvim",
    name="Takvim",
    index="https://www.takvim.com.tr/sitemap/post.xml",
    month_file=_TURKUVAZ_MONTHS,
    earliest=Month(2009, 2),
    notes="Every month since February 2009. No headlines.",
)


TIMETURK = ChunkedSitemap(
    id="timeturk",
    name="Timeturk",
    index="https://www.timeturk.com/sitemap.xml",
    chunk_file=r"/sitemap-posts-(?P<n>\d+)\.xml$",
    chunk_order="newest-first",
    entry_order="newest-first",
    earliest=Month(2014, 1),
    notes=(
        "Numbered files of 1,000 articles each, the newest first; its oldest articles are dated "
        "January 2014. No headlines."
    ),
)


TURKGUN = MonthlySitemap(
    id="turkgun",
    name="Türkgün",
    index="https://www.turkgun.com/sitemap.xml",
    month_file=r"/sitemap/news-(?P<year>\d{4})-(?P<month>\d{2})\.xml$",
    titles="image",
    earliest=Month(2019, 3),
    notes="Every month since March 2019. Headlines come from the image titles in its sitemaps.",
)


YENI_ASIR = MonthlySitemap(
    id="yeni-asir",
    name="Yeni Asır",
    index="https://www.yeniasir.com.tr/sitemap/post.xml",
    month_file=_TURKUVAZ_MONTHS,
    earliest=Month(2009, 7),
    notes="A regional paper of İzmir. Every month since July 2009. No headlines.",
)


BUILTIN: tuple[Outlet, ...] = (
    CUMHURIYET,
    EURONEWS_TR,
    TRT_HABER,
    STAR,
    AKSAM,
    SOZCU,
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
    OZGUR_KOCAELI,
    SABAH,
    TAKVIM,
    TIMETURK,
    TURKGUN,
    YENI_ASIR,
)
"""The default outlets: search reads them unless told otherwise."""
OPT_IN: tuple[Outlet, ...] = (SPUTNIK_TR,)
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
