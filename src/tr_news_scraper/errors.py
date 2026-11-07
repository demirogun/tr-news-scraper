"""Errors raised by tr_news_scraper.

Every exception the library raises on purpose subclasses ``TrNewsError``, so callers can
catch the library's failures without catching unrelated ones.
"""

from __future__ import annotations


class TrNewsError(Exception):
    """Base class for all tr_news_scraper errors."""


class HttpError(TrNewsError):
    """A request to a news site could not be made or completed."""

    def __init__(self, url: str, problem: str) -> None:
        super().__init__(f"{problem}: {url}")
        self.url = url


class HostNotAllowed(HttpError):
    """The URL isn't HTTPS, its host isn't allowed, or it points into a private network."""

    def __init__(self, url: str, reason: str) -> None:
        super().__init__(url, f"refused, {reason}")
        self.reason = reason
