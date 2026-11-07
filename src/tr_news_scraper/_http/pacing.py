"""Per-host pacing: one request in flight per host, and request starts spaced by an interval."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

from tr_news_scraper._http.clock import Clock


@dataclass(slots=True)
class _HostTurns:
    lock: threading.Lock = field(default_factory=threading.Lock)
    last_start: float | None = None


class HostPacer:
    """Hands out turns per host. Different hosts never wait for each other."""

    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._hosts: dict[str, _HostTurns] = {}
        self._guard = threading.Lock()

    @contextmanager
    def turn(self, host: str, interval: float) -> Iterator[None]:
        """Wait until ``interval`` seconds have passed since this host's last turn began, then
        hold the host for the duration of the ``with`` block."""
        with self._guard:
            turns = self._hosts.setdefault(host, _HostTurns())
        with turns.lock:
            if turns.last_start is not None:
                wait = interval - (self._clock.monotonic() - turns.last_start)
                if wait > 0:
                    self._clock.sleep(wait)
            turns.last_start = self._clock.monotonic()
            yield
