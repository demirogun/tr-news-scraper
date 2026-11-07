"""The HTTP client: an honest identity, no cookies, and only HTTPS hosts the caller allows."""

from __future__ import annotations

import codecs
import logging
import random
import re
import threading
import unicodedata
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from datetime import datetime
from http.cookiejar import DefaultCookiePolicy
from pathlib import Path
from types import TracebackType
from typing import Self
from urllib.parse import urlsplit

import requests

from tr_news_scraper import __version__
from tr_news_scraper._http.clock import Clock, SystemClock
from tr_news_scraper._http.pacing import HostPacer
from tr_news_scraper._http.retry import (
    BLOCKED_STATUSES,
    MAX_RETRY_AFTER,
    RETRY_STATUSES,
    parse_retry_after,
    retry_delay,
)
from tr_news_scraper._http.robots import MAX_ROBOTS_BYTES, RobotsPolicy
from tr_news_scraper._http.safety import check_url
from tr_news_scraper.errors import Blocked, RequestFailed, ResponseTooLarge, RobotsDisallowed

logger = logging.getLogger("tr_news_scraper.http")

PROJECT_URL = "https://github.com/demirogun/tr-news-scraper"
ACCEPT_LANGUAGE = "tr-TR,tr;q=0.9,en;q=0.5"
_UNSAFE_IN_CONTACT = frozenset("();")
_HEADER_CHARSET = re.compile(r"charset\s*=\s*[\"']?([\w.:-]+)", re.IGNORECASE)
_XML_ENCODING = re.compile(rb"^\s*<\?xml[^>]*\bencoding\s*=\s*[\"']([\w.:-]+)[\"']", re.IGNORECASE)
_META_CHARSET = re.compile(rb"<meta[^>]+charset\s*=\s*[\"']?([\w.:-]+)", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class HttpConfig:
    """Politeness and safety limits; the defaults are the ones the library is meant to run with."""

    contact: str | None = None
    obey_robots: bool = True
    min_interval: float = 1.0
    connect_timeout: float = 10.0
    read_timeout: float = 30.0
    max_retries: int = 3
    max_bytes: int = 64 * 1024**2
    cache_dir: Path | None = None
    cache_max_bytes: int = 2 * 1024**3

    def __post_init__(self) -> None:
        if self.contact is not None and not _is_safe_contact(self.contact):
            raise ValueError(
                "contact must be printable ASCII without parentheses or semicolons, "
                "for example 'mailto:you@example.org'"
            )
        for name in ("connect_timeout", "read_timeout", "max_bytes", "cache_max_bytes"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        for name in ("min_interval", "max_retries"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} can't be negative")

    @property
    def user_agent(self) -> str:
        """The User-Agent sent with every request. It can't be replaced, only extended."""
        details = f"+{PROJECT_URL}" + (f"; {self.contact}" if self.contact else "")
        return f"tr-news-scraper/{__version__} ({details})"


@dataclass(frozen=True, slots=True)
class Response:
    """A completed response. Header names are lowercase."""

    url: str
    status: int
    headers: Mapping[str, str]
    content: bytes
    fetched_at: datetime
    from_cache: bool = False

    def text(self) -> str:
        """Decode the body (header charset, then the document's own declaration, then UTF-8)."""
        encoding = _charset(self.headers.get("content-type", ""), self.content)
        return unicodedata.normalize("NFC", self.content.decode(encoding, errors="replace"))


class Http:
    """Fetches pages from news sites, politely and safely. Use one instance per search."""

    def __init__(
        self,
        config: HttpConfig | None = None,
        *,
        clock: Clock | None = None,
        jitter: Callable[[], float] | None = None,
    ) -> None:
        self.config = config or HttpConfig()
        self._clock: Clock = clock or SystemClock()
        self._jitter = jitter or random.SystemRandom().random
        self._session = requests.Session()
        self._session.cookies.set_policy(DefaultCookiePolicy(allowed_domains=[]))
        self._session.headers.update(
            {"User-Agent": self.config.user_agent, "Accept-Language": ACCEPT_LANGUAGE}
        )
        self._robots = RobotsPolicy(self._fetch_robots, self._clock)
        self._pacer = HostPacer(self._clock)
        self._override_warned: set[str] = set()
        self._warn_lock = threading.Lock()

    def get(self, url: str, *, allowed_hosts: Collection[str], accept: str = "*/*") -> Response:
        """Fetch ``url`` if the caller allows its host and the site's robots.txt allows us.

        Raises ``HostNotAllowed`` or ``RobotsDisallowed`` before any request to ``url``.
        """
        check_url(url, allowed_hosts)
        interval = self.config.min_interval
        if not self.config.obey_robots:
            self._warn_override_once(url)
        elif not self._robots.allows(url):
            logger.warning("robots.txt disallows %s", url)
            raise RobotsDisallowed(url)
        else:
            interval = max(interval, self._robots.crawl_delay(url) or 0.0)
        return self._fetch(url, accept, interval, limit=self.config.max_bytes)

    def _fetch_robots(self, robots_url: str) -> tuple[int | None, bytes]:
        try:
            response = self._fetch(
                robots_url,
                "text/plain",
                self.config.min_interval,
                limit=MAX_ROBOTS_BYTES,
                truncate=True,
            )
        except (Blocked, RequestFailed) as failure:
            return failure.status, b""
        return response.status, response.content

    def _warn_override_once(self, url: str) -> None:
        host = urlsplit(url).hostname or url
        with self._warn_lock:
            if host in self._override_warned:
                return
            self._override_warned.add(host)
        logger.warning(
            "robots.txt check disabled by the user for %s; requests may break the site's rules",
            host,
        )

    def _fetch(
        self, url: str, accept: str, interval: float, *, limit: int, truncate: bool = False
    ) -> Response:
        """One paced request, retried on connection errors, timeouts, 429 and 5xx."""
        host = urlsplit(url).hostname or ""
        attempt = 0
        while True:
            attempt += 1
            status: int | None = None
            headers: Mapping[str, str] = {}
            try:
                with (
                    self._pacer.turn(host, interval),
                    self._session.get(
                        url,
                        headers={"Accept": accept},
                        timeout=(self.config.connect_timeout, self.config.read_timeout),
                        allow_redirects=False,
                        stream=True,
                    ) as reply,
                ):
                    status = reply.status_code
                    if status in BLOCKED_STATUSES:
                        logger.warning("%s refused the request with HTTP %d: %s", host, status, url)
                        raise Blocked(url, status)
                    if status < 400:
                        return Response(
                            url=reply.url,
                            status=status,
                            headers={name.lower(): value for name, value in reply.headers.items()},
                            content=_read(reply, url, limit, truncate=truncate),
                            fetched_at=self._clock.now(),
                        )
                    headers = reply.headers
                problem = f"HTTP {status}"
            except requests.exceptions.SSLError as error:
                raise RequestFailed(url, f"TLS error: {error}", attempts=attempt) from error
            except (
                requests.ConnectionError,
                requests.Timeout,
                requests.exceptions.ChunkedEncodingError,
            ) as error:
                problem = type(error).__name__
            except requests.RequestException as error:
                raise RequestFailed(url, type(error).__name__, attempts=attempt) from error
            now = self._clock.now()
            delay = retry_delay(status, headers, attempt, now=now, jitter=self._jitter)
            if delay is None:
                reason = _no_retry_reason(status, headers, problem, now)
                raise RequestFailed(url, reason, attempts=attempt, status=status)
            if attempt > self.config.max_retries:
                raise RequestFailed(url, problem, attempts=attempt, status=status)
            logger.warning(
                "retrying %s in %.1f s after %s (attempt %d of %d)",
                url,
                delay,
                problem,
                attempt,
                self.config.max_retries + 1,
            )
            self._clock.sleep(delay)

    def close(self) -> None:
        """Release the connection pool."""
        self._session.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


def _read(reply: requests.Response, url: str, limit: int, *, truncate: bool) -> bytes:
    """Read the decompressed body; past ``limit``, refuse it (or cut it, for robots.txt)."""
    chunks: list[bytes] = []
    size = 0
    for chunk in reply.iter_content(chunk_size=64 * 1024):
        size += len(chunk)
        if size > limit:
            if not truncate:
                raise ResponseTooLarge(url, limit)
            chunks.append(chunk[: len(chunk) - (size - limit)])
            break
        chunks.append(chunk)
    return b"".join(chunks)


def _no_retry_reason(
    status: int | None, headers: Mapping[str, str], problem: str, now: datetime
) -> str:
    if status in RETRY_STATUSES:
        advised = parse_retry_after(headers.get("Retry-After"), now=now)
        return (
            f"{problem}; the server asked us to wait {advised:.0f} s, "
            f"longer than the {MAX_RETRY_AFTER:.0f} s we're willing to wait"
        )
    return problem


def _is_safe_contact(contact: str) -> bool:
    return (
        contact == contact.strip()
        and bool(contact)
        and all(32 <= ord(char) < 127 for char in contact)
        and not _UNSAFE_IN_CONTACT.intersection(contact)
    )


def _charset(content_type: str, body: bytes) -> str:
    if body.startswith(codecs.BOM_UTF8):
        return "utf-8-sig"
    labels: list[str] = []
    if from_header := _HEADER_CHARSET.search(content_type):
        labels.append(from_header.group(1))
    head = body[:4096]
    for pattern in (_XML_ENCODING, _META_CHARSET):
        if declared := pattern.search(head):
            labels.append(declared.group(1).decode("ascii"))
    for label in labels:
        try:
            return codecs.lookup(label).name
        except LookupError:
            continue
    return "utf-8"
