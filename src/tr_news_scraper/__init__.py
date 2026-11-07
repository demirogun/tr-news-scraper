"""Search Turkish news archives by keyword and date range, politely."""

from __future__ import annotations

import logging
from importlib.metadata import version

__version__ = version("tr-news-scraper")
__all__: list[str] = []

logging.getLogger(__name__).addHandler(logging.NullHandler())
