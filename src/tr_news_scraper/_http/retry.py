"""When a failed request is worth retrying, and how long to wait first."""

from __future__ import annotations

import email.utils
from collections.abc import Callable, Mapping
from datetime import UTC, datetime

RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
BLOCKED_STATUSES = frozenset({401, 403, 451})
MAX_RETRY_AFTER = 300.0


def parse_retry_after(value: str | None, *, now: datetime) -> float | None:
    """Seconds to wait according to a ``Retry-After`` header (seconds or an HTTP date).

    Returns ``None`` when the header is missing or unusable, and ``0.0`` for a date in the past.
    """
    if value is None:
        return None
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        when = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max((when - now).total_seconds(), 0.0)


def retry_delay(
    status: int | None,
    headers: Mapping[str, str],
    attempt: int,
    *,
    now: datetime,
    jitter: Callable[[], float],
) -> float | None:
    """Return the seconds to wait before retrying, or ``None`` if the request must not be retried.

    ``status`` is ``None`` for connection errors and timeouts. ``attempt`` counts from 1.
    """
    if status is not None and status not in RETRY_STATUSES:
        return None
    advised = parse_retry_after(headers.get("Retry-After"), now=now)
    if advised is not None:
        return advised if advised <= MAX_RETRY_AFTER else None
    return float(2**attempt) + jitter()
