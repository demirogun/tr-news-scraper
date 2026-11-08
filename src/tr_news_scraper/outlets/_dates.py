"""Dates from news archives: W3C datetimes in sitemaps, and day strings in search results."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

# The outlets publish in Türkiye. A time without an offset is read in this zone, which also knows
# the UTC+2 winters before September 2016.
ISTANBUL = ZoneInfo("Europe/Istanbul")


def parse_lastmod(text: str | None) -> datetime | None:
    """A sitemap ``<lastmod>`` value as a timezone-aware datetime.

    A value with an offset or ``Z`` keeps it. A date, or a time without an offset, is read as
    Europe/Istanbul. Returns ``None`` for a missing, blank or unreadable value.
    """
    if text is None or not text.strip():
        return None
    try:
        parsed = datetime.fromisoformat(text.strip())
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ISTANBUL)
    return parsed


def parse_day(text: str | None, fmt: str) -> date | None:
    """A calendar day written in the ``strptime`` format ``fmt``, or ``None`` if the text
    doesn't fit it."""
    if text is None:
        return None
    try:
        # A calendar day has no time zone to attach.
        return datetime.strptime(text.strip(), fmt).date()  # noqa: DTZ007
    except ValueError:
        return None
