"""robots.txt per RFC 9309: fetch it once per host, follow its rules, keep them for a day.

Rules are parsed with protego, so wildcards (``*``), end anchors (``$``) and longest-match
precedence behave the same on every supported Python. Python 3.12's own parser ignores them.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

from protego import Protego

from tr_news_scraper._http.clock import Clock

USER_AGENT_PRODUCT = "tr-news-scraper"
MAX_ROBOTS_BYTES = 500 * 1024
RULES_TTL_SECONDS = 24 * 60 * 60.0

RobotsFetcher = Callable[[str], tuple[int | None, bytes]]
"""Fetches a robots.txt URL; returns ``(status, body)``, or ``(None, b"")`` if the network fails."""


@dataclass(frozen=True, slots=True)
class RobotsRules:
    """What one host's robots.txt means for us: allow all, block all, or follow parsed rules."""

    allow_all: bool
    parser: Protego | None
    fetched_at: float

    def allows(self, url: str) -> bool:
        if self.parser is None:
            return self.allow_all
        return bool(self.parser.can_fetch(url, USER_AGENT_PRODUCT))

    @property
    def crawl_delay(self) -> float | None:
        if self.parser is None:
            return None
        delay = self.parser.crawl_delay(USER_AGENT_PRODUCT)
        return None if delay is None else float(delay)


class RobotsPolicy:
    """Answers "may tr-news-scraper fetch this URL?" for any host."""

    def __init__(self, fetch: RobotsFetcher, clock: Clock) -> None:
        self._fetch = fetch
        self._clock = clock
        self._rules: dict[str, RobotsRules] = {}
        self._host_locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def allows(self, url: str) -> bool:
        return self._rules_for(url).allows(url)

    def crawl_delay(self, url: str) -> float | None:
        return self._rules_for(url).crawl_delay

    def _rules_for(self, url: str) -> RobotsRules:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        with self._guard:
            host_lock = self._host_locks.setdefault(origin, threading.Lock())
        with host_lock:
            cached = self._rules.get(origin)
            now = self._clock.monotonic()
            if cached is not None and now - cached.fetched_at < RULES_TTL_SECONDS:
                return cached
            status, body = self._fetch(f"{origin}/robots.txt")
            rules = _interpret(status, body, now)
            self._rules[origin] = rules
            return rules


def _interpret(status: int | None, body: bytes, fetched_at: float) -> RobotsRules:
    """Map a robots.txt response to rules, following RFC 9309 section 2.3.1."""
    if status is not None and 200 <= status < 300:
        text = body[:MAX_ROBOTS_BYTES].decode("utf-8", errors="replace").lstrip("﻿")
        return RobotsRules(allow_all=False, parser=Protego.parse(text), fetched_at=fetched_at)
    if status is not None and 300 <= status < 500 and status != 429:
        # 4xx: "unavailable", so no restrictions. A redirect still unresolved after the
        # client's redirect limit counts as unavailable too (RFC 9309, 2.3.1.2).
        return RobotsRules(allow_all=True, parser=None, fetched_at=fetched_at)
    # 5xx, 429 and network failures: "unreachable", so stay away from the whole host.
    return RobotsRules(allow_all=False, parser=None, fetched_at=fetched_at)
