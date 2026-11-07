"""Errors raised by tr_news_scraper.

Every exception the library raises on purpose subclasses ``TrNewsError``, so callers can
catch the library's failures without catching unrelated ones.
"""

from __future__ import annotations


class TrNewsError(Exception):
    """Base class for all tr_news_scraper errors."""
