"""search(): keywords and a past date range in, one table of matching articles out (internal)."""

from __future__ import annotations

import re
from collections.abc import Iterable
from contextlib import suppress
from datetime import date, datetime

from tr_news_scraper.matching import tr_lower
from tr_news_scraper.outlets import MonthlySitemap, Outlet, SiteSearch, builtin, get

_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
_OUTLET_KINDS = (MonthlySitemap, SiteSearch)


def parse_keywords(keywords: str | Iterable[str]) -> tuple[str, ...]:
    """The keywords to search for (S1). A ``str`` is one keyword. Blank and repeated keywords
    are dropped; a repeat differs only in case and keeps the first spelling."""
    items: Iterable[object] = [keywords] if isinstance(keywords, str) else keywords
    kept: dict[str, str] = {}
    for item in items:
        if not isinstance(item, str):
            raise TypeError(f"keywords must be strings, not {type(item).__name__}")
        text = item.strip()
        if text:
            kept.setdefault(tr_lower(text), text)
    if not kept:
        raise ValueError("give at least one keyword, such as 'deprem'")
    return tuple(kept.values())


def parse_day(value: object, name: str) -> date:
    """A day in Türkiye, given as a ``date`` or ``"YYYY-MM-DD"`` (S1)."""
    if isinstance(value, datetime):
        raise TypeError(f"{name} must be a date, not a datetime: a range is whole days in Türkiye")
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a date or 'YYYY-MM-DD', not {type(value).__name__}")
    text = value.strip()
    if _DAY.fullmatch(text):
        with suppress(ValueError):
            return date.fromisoformat(text)
    raise ValueError(f"{name} must be a date or 'YYYY-MM-DD', such as '2023-02-01', not {value!r}")


def parse_range(start: date | str, end: date | str) -> tuple[date, date]:
    """The range [start, end): whole days in Türkiye, the end excluded (S1)."""
    first, after = parse_day(start, "start"), parse_day(end, "end")
    if first >= after:
        raise ValueError(
            f"the start ({first}) must be before the end ({after}); "
            "the end is the day after the last day you want"
        )
    return first, after


def resolve_outlets(
    outlets: str | Outlet | Iterable[str | Outlet] | None,
) -> tuple[Outlet, ...]:
    """The outlets to search, in the order given; every built-in outlet by default (S1)."""
    if outlets is None:
        return builtin()
    items: Iterable[object] = [outlets] if isinstance(outlets, (str, *_OUTLET_KINDS)) else outlets
    chosen: dict[str, Outlet] = {}
    for item in items:
        outlet = get(item) if isinstance(item, str) else item
        if not isinstance(outlet, _OUTLET_KINDS):
            raise TypeError(f"outlets must be outlet ids or definitions, not {type(item).__name__}")
        if outlet.id in chosen:
            raise ValueError(f"two outlets share the id {outlet.id!r}")
        chosen[outlet.id] = outlet
    if not chosen:
        raise ValueError("choose at least one outlet, or leave outlets out to search them all")
    return tuple(chosen.values())
