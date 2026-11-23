"""What an article page states about itself in structured form (internal).

fetch reads a page's JSON-LD first (F3a) and falls back to what trafilatura finds. Everything here
is a pure function over text: nothing makes a request, and nothing a page says is logged (F13).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from datetime import datetime
from typing import Any

from tr_news_scraper.outlets._dates import ISTANBUL

ARTICLE_TYPES = frozenset(
    {
        "NewsArticle",
        "Article",
        "ReportageNews",
        "AnalysisNewsArticle",
        "OpinionNewsArticle",
        "BackgroundNewsArticle",
        "BlogPosting",
        "LiveBlogPosting",
    }
)
"""The JSON-LD types that describe an article (schema.org)."""
MAX_JSON_LD_CHARACTERS = 1_000_000
"""A JSON-LD block longer than this, about 1 MB, isn't read."""
_MAX_DEPTH = 4
"""How deep lists and ``@graph`` members are followed."""


def json_ld_objects(blocks: Iterable[str]) -> list[dict[str, Any]]:
    """Every JSON object in the JSON-LD blocks, in page order, ``@graph`` members included.

    A block holds one object, a list, or an object with an ``@graph``. A block over
    ``MAX_JSON_LD_CHARACTERS``, or one that isn't JSON even with raw line breaks allowed inside
    strings, is skipped.
    """
    objects: list[dict[str, Any]] = []
    for block in blocks:
        if len(block) > MAX_JSON_LD_CHARACTERS:
            continue
        try:
            data = json.loads(block, strict=False)
        except (ValueError, RecursionError):
            continue
        objects.extend(_objects(data, depth=0))
    return objects


def find_article(objects: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
    """The first object whose ``@type``, a name or a list of names, is a kind of article."""
    for item in objects:
        if _types(item.get("@type")) & ARTICLE_TYPES:
            return item
    return None


def read_time(value: object) -> datetime | None:
    """An ISO 8601 date or time, such as JSON-LD's ``datePublished``, in Europe/Istanbul.

    A time with an offset or ``Z`` keeps its instant; one without is Türkiye's time; a date alone
    gives midnight, meaning only the day is known. A list gives its first text. Anything else,
    including a time outside the calendar, gives ``None``.
    """
    if isinstance(value, list):
        value = next((item for item in value if isinstance(item, str)), None)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=ISTANBUL)
        return parsed.astimezone(ISTANBUL)
    except (ValueError, OverflowError):
        return None


def _objects(data: object, *, depth: int) -> Iterator[dict[str, Any]]:
    if depth > _MAX_DEPTH:
        return
    if isinstance(data, list):
        for item in data:
            yield from _objects(item, depth=depth + 1)
    elif isinstance(data, dict):
        yield data
        if "@graph" in data:
            yield from _objects(data["@graph"], depth=depth + 1)


def _types(value: object) -> set[str]:
    """Type names without a schema.org prefix: ``https://schema.org/NewsArticle`` and
    ``schema:NewsArticle`` are both ``NewsArticle``."""
    names = [value] if isinstance(value, str) else value if isinstance(value, list) else []
    return {name.rsplit("/", 1)[-1].rsplit(":", 1)[-1] for name in names if isinstance(name, str)}
