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


class RobotsDisallowed(HttpError):
    """The site's robots.txt doesn't allow tr-news-scraper to fetch this URL."""

    def __init__(self, url: str) -> None:
        super().__init__(url, "robots.txt disallows fetching")


class Blocked(HttpError):
    """The site refused the request (HTTP 401, 403 or 451). It is never retried."""

    def __init__(self, url: str, status: int) -> None:
        super().__init__(url, f"the site refused the request with HTTP {status}")
        self.status = status


class ResponseTooLarge(HttpError):
    """The body, after decompression, grew past the configured size cap."""

    def __init__(self, url: str, limit: int) -> None:
        super().__init__(url, f"the response is larger than {limit} bytes")
        self.limit = limit


class RequestFailed(HttpError):
    """Retries ran out, or the server answered with an error that retrying can't fix."""

    def __init__(self, url: str, problem: str, *, attempts: int, status: int | None = None) -> None:
        plural = "" if attempts == 1 else "s"
        super().__init__(url, f"{problem} (after {attempts} attempt{plural})")
        self.problem = problem
        self.attempts = attempts
        self.status = status
