"""Search Turkish news archives by keyword and date range, politely."""

from __future__ import annotations

import logging

from tr_news_scraper._coverage import coverage
from tr_news_scraper._fetch import fetch
from tr_news_scraper._fetched import FetchResult
from tr_news_scraper._search import search
from tr_news_scraper._table import SearchResult
from tr_news_scraper._version import __version__

__all__ = ["FetchResult", "SearchResult", "__version__", "coverage", "fetch", "search"]

logging.getLogger(__name__).addHandler(logging.NullHandler())
