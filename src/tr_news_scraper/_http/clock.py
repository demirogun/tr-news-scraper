"""Time for the http layer, injectable so pacing and retry tests never really sleep."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    """Wall-clock time for timestamps, monotonic time for intervals, and sleeping."""

    def now(self) -> datetime:
        """Return the current time, timezone-aware, in UTC."""
        ...

    def monotonic(self) -> float:
        """Return seconds from an arbitrary start; never goes backwards."""
        ...

    def sleep(self, seconds: float) -> None:
        """Block the calling thread for ``seconds``."""
        ...


class SystemClock:
    """The real clock."""

    def now(self) -> datetime:
        return datetime.now(UTC)

    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)
