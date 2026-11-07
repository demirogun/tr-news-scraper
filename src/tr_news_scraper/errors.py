"""Errors raised by tr_news_scraper.

Every exception the library raises on purpose subclasses ``TrNewsError``, so callers can
catch the library's failures without catching unrelated ones.
"""

from __future__ import annotations

from collections.abc import Mapping


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


class NotCached(HttpError):
    """Offline mode was requested, and the URL isn't in the cache."""

    def __init__(self, url: str) -> None:
        super().__init__(url, "offline, and not in the cache")


class OutletFailed(TrNewsError):
    """Nothing could be read from an outlet's archive: its sitemap index, or every file or
    page the date range needed, failed."""

    def __init__(self, outlet: str, reason: str) -> None:
        super().__init__(f"{outlet}: {reason}")
        self.outlet = outlet
        self.reason = reason


class SearchFailed(TrNewsError):
    """Every outlet in a search failed, so there is nothing to return. ``failures`` maps each
    outlet's id to its reason."""

    def __init__(self, failures: Mapping[str, str], hint: str | None = None) -> None:
        lines = [f"  {outlet}: {reason}" for outlet, reason in failures.items()]
        super().__init__("\n".join(["every outlet failed:", *lines, *([hint] if hint else [])]))
        self.failures = dict(failures)


class RequestFailed(HttpError):
    """Retries ran out, or the server answered with an error that retrying can't fix."""

    def __init__(self, url: str, problem: str, *, attempts: int, status: int | None = None) -> None:
        plural = "" if attempts == 1 else "s"
        super().__init__(url, f"{problem} (after {attempts} attempt{plural})")
        self.problem = problem
        self.attempts = attempts
        self.status = status
