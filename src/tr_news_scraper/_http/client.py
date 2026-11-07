"""The HTTP client: an honest identity, no cookies, and only HTTPS hosts the caller allows."""

from __future__ import annotations

import codecs
import logging
import re
import threading
import unicodedata
from collections.abc import Collection, Mapping
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
from tr_news_scraper._http.robots import RobotsPolicy
from tr_news_scraper._http.safety import check_url
from tr_news_scraper.errors import RobotsDisallowed

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

    def __init__(self, config: HttpConfig | None = None, *, clock: Clock | None = None) -> None:
        self.config = config or HttpConfig()
        self._clock: Clock = clock or SystemClock()
        self._session = requests.Session()
        self._session.cookies.set_policy(DefaultCookiePolicy(allowed_domains=[]))
        self._session.headers.update(
            {"User-Agent": self.config.user_agent, "Accept-Language": ACCEPT_LANGUAGE}
        )
        self._robots = RobotsPolicy(self._fetch_robots, self._clock)
        self._override_warned: set[str] = set()
        self._warn_lock = threading.Lock()

    def get(self, url: str, *, allowed_hosts: Collection[str], accept: str = "*/*") -> Response:
        """Fetch ``url`` if the caller allows its host and the site's robots.txt allows us.

        Raises ``HostNotAllowed`` or ``RobotsDisallowed`` before any request to ``url``.
        """
        check_url(url, allowed_hosts)
        if not self.config.obey_robots:
            self._warn_override_once(url)
        elif not self._robots.allows(url):
            logger.warning("robots.txt disallows %s", url)
            raise RobotsDisallowed(url)
        return self._send(url, accept)

    def _fetch_robots(self, robots_url: str) -> tuple[int | None, bytes]:
        try:
            response = self._send(robots_url, "text/plain")
        except requests.RequestException:
            return None, b""
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

    def _send(self, url: str, accept: str) -> Response:
        reply = self._session.get(
            url,
            headers={"Accept": accept},
            timeout=(self.config.connect_timeout, self.config.read_timeout),
            allow_redirects=False,
        )
        return Response(
            url=reply.url,
            status=reply.status_code,
            headers={name.lower(): value for name, value in reply.headers.items()},
            content=reply.content,
            fetched_at=self._clock.now(),
        )

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
