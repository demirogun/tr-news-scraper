"""Turkish news outlets and their archives: the plug-in API.

An outlet is data, not code: where its archive is and how to read it. One engine reads every
archive the same way, through the library's polite HTTP client. Three kinds of archive are
supported:

- ``MonthlySitemap``: a sitemap index that lists sitemap files by month;
- ``ChunkedSitemap``: a sitemap index that lists numbered files of articles, in publication order;
- ``SiteSearch``: a search endpoint, allowed by robots.txt, with the newest results first.

``builtin()`` lists the outlets search uses by default, and ``get()`` finds one by id. An outlet
of your own is defined the same way and passed to search alongside them.
"""

from tr_news_scraper.outlets._builtin import builtin, get
from tr_news_scraper.outlets._model import (
    Candidate,
    ChunkedSitemap,
    Month,
    MonthlySitemap,
    Outlet,
    SiteSearch,
)

__all__ = [
    "Candidate",
    "ChunkedSitemap",
    "Month",
    "MonthlySitemap",
    "Outlet",
    "SiteSearch",
    "builtin",
    "get",
]
