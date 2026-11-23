"""What an article page states about itself in structured form (internal).

fetch reads a page's JSON-LD, ``<h1>`` and meta tags first (F3a–F3e) and falls back to what
trafilatura finds. Nothing here makes a request, and nothing a page says is logged (F13).
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any

import lxml.html
from lxml import etree

from tr_news_scraper.matching import fold
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
LEAD_TAGS = ("h2", "h3", "p", "div", "span", "strong")
"""The elements a visible lead may be in."""
LEAD_SIMILARITY = 0.98
"""How alike a lead and the description, or a lead and the text's start, must be to count."""
_MAX_DEPTH = 4
"""How deep lists and ``@graph`` members are followed."""
_SEPARATOR = re.compile(r"\s+[-|–—]\s+")
_INVISIBLE = frozenset({"noscript", "template"})
_NO_DISPLAY = re.compile(r"display\s*:\s*none", re.IGNORECASE)
_EMAIL = re.compile(r"[^\s/,;|()<>]+@[^\s/,;|()<>]+")
_NAME_EDGES = " /,;|-–—·()<>"


@dataclass(frozen=True, slots=True)
class PageFacts:
    """What a page states about its article: its JSON-LD article object, ``<h1>`` texts and meta
    tags, and the visible lead its description points to. Texts have their spaces collapsed and
    are NFC."""

    article: bool = False
    """Whether the page's JSON-LD has an article object."""
    headline: str | None = None
    """The article object's ``headline``."""
    published: datetime | None = None
    """The article object's ``datePublished``, in Europe/Istanbul (F3c)."""
    authors: tuple[str, ...] = ()
    """The article object's author names, each once."""
    publisher: str | None = None
    description: str | None = None
    """The article object's ``description``; without one, ``og:description`` or the
    ``description`` meta tag."""
    h1s: tuple[str, ...] = ()
    """The texts of the page's ``<h1>`` elements, in page order."""
    og_title: str | None = None
    lead: str | None = None
    """The text of the first visible element that the description matches (F3d)."""


def read_page(html: str) -> PageFacts:
    """The structured facts a page states. Its parsed tree is freed before this returns (F3g)."""
    try:
        parser = lxml.html.HTMLParser(encoding="utf-8")
        root = lxml.html.document_fromstring(html.encode("utf-8"), parser=parser)
    except (etree.ParserError, ValueError):
        return PageFacts()
    blocks = [script.text or "" for script in root.iter("script") if _is_json_ld(script)]
    article = find_article(json_ld_objects(blocks)) or {}
    tags = _meta_tags(root)
    headline = line(_text(article.get("headline")))
    og_title = line(tags.get("og:title"))
    h1s = tuple(text for h1 in root.iter("h1") if (text := line(h1.text_content())))
    description = (
        line(_text(article.get("description")))
        or line(tags.get("og:description"))
        or line(tags.get("description"))
    )
    titles = [text for text in (headline, og_title, *h1s) if text]
    body = root.find("body")
    lead = None
    if description and body is not None and not any(alike(description, t) for t in titles):
        lead = _visible_lead(body, description)
    return PageFacts(
        article=bool(article),
        headline=headline,
        published=read_time(article.get("datePublished")),
        authors=_names(article.get("author")),
        publisher=line(_name(article.get("publisher"))),
        description=description,
        h1s=h1s,
        og_title=og_title,
        lead=lead,
    )


def choose_headline(facts: PageFacts, fallback: str | None, outlet_name: str) -> str | None:
    """The headline (F3b): the first ``<h1>`` whose text equals the JSON-LD headline,
    ``og:title`` or trafilatura's title (``fallback``); else the JSON-LD headline; else
    ``fallback``. Texts are compared with spaces collapsed, NFC and the outlet's name trimmed."""
    candidates = {
        _comparable(text, outlet_name)
        for text in (facts.headline, facts.og_title, fallback)
        if text
    }
    for h1 in facts.h1s:
        if _comparable(h1, outlet_name) in candidates:
            return h1
    return facts.headline or fallback


def choose_author(facts: PageFacts, fallback: str | None, outlet_name: str) -> str | None:
    """The byline (F3e): the JSON-LD author names joined by ", ", without a name equal to the
    publisher's or the outlet's; trafilatura's byline (``fallback``) when no name is left."""
    dropped = {fold(name) for name in (facts.publisher, outlet_name) if name}
    kept = [name for name in facts.authors if fold(name) not in dropped]
    return ", ".join(kept) if kept else fallback


def with_lead(text: str | None, lead: str | None) -> str | None:
    """``text`` with the visible lead as its first paragraph, unless the text already has it:
    at its start, or as one of its paragraphs, word for word or 98% alike (F3d)."""
    if text is None or lead is None:
        return text
    if lead in text or alike(lead, text[: len(lead)]):
        return text
    if any(alike(lead, paragraph) for paragraph in text.split("\n")):
        return text
    return f"{lead}\n{text}"


def clean_headline(title: str | None, outlet_name: str) -> str | None:
    """A page's headline without a trailing part that names the outlet, like "… - Sözcü
    Gazetesi" or "… | STAR". The outlet is recognized by the first word of its name."""
    if title is None or not outlet_name.split():
        return title
    separators = list(_SEPARATOR.finditer(title))
    if not separators:
        return title
    last = separators[-1]
    head = title[: last.start()].strip()
    if head and fold(outlet_name.split()[0]) in fold(title[last.end() :]):
        return head
    return title


def line(text: str | None) -> str | None:
    """``text`` on one line: runs of spaces collapsed, NFC; ``None`` when nothing is left."""
    if not text:
        return None
    return unicodedata.normalize("NFC", " ".join(text.split())) or None


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


def _is_json_ld(script: lxml.html.HtmlElement) -> bool:
    kind = (script.get("type") or "").partition(";")[0].strip().lower()
    return kind == "application/ld+json"


def _meta_tags(root: lxml.html.HtmlElement) -> dict[str, str]:
    """Each meta tag's content by its lowercased ``property`` or ``name``; the first one wins."""
    found: dict[str, str] = {}
    for meta in root.iter("meta"):
        key = (meta.get("property") or meta.get("name") or "").strip().lower()
        content = meta.get("content")
        if key and content is not None:
            found.setdefault(key, content)
    return found


def _text(value: object) -> str | None:
    """A JSON-LD value as text: a string, or the first string in a list."""
    if isinstance(value, list):
        value = next((item for item in value if isinstance(item, str)), None)
    return value if isinstance(value, str) else None


def _name(value: object) -> str | None:
    """The name of a person or organization: an object's ``name``, a string, or a list's first."""
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, dict):
        return _text(value.get("name"))
    return value if isinstance(value, str) else None


def _names(value: object) -> tuple[str, ...]:
    """Every author name once, in order, without email addresses; links and nameless entries
    are skipped."""
    found: dict[str, str] = {}
    for item in value if isinstance(value, list) else [value]:
        name = line(_EMAIL.sub(" ", _name(item) or ""))
        name = line(name.strip(_NAME_EDGES)) if name else None
        if name and not name.lower().startswith(("http://", "https://", "www.")):
            found.setdefault(fold(name), name)
    return tuple(found.values())


def _comparable(text: str, outlet_name: str) -> str | None:
    return clean_headline(line(text), outlet_name)


def _visible_lead(body: lxml.html.HtmlElement, description: str) -> str | None:
    """The text of the first visible lead element that matches ``description`` (F3d)."""
    shortest = len(description) * LEAD_SIMILARITY / (2 - LEAD_SIMILARITY)
    for element in body.iter(*LEAD_TAGS):
        raw = element.text_content()
        if len(raw) < shortest:
            continue
        text = line(raw)
        if text and alike(description, text) and _visible(element):
            return text
    return None


def _visible(element: lxml.html.HtmlElement) -> bool:
    for node in (element, *element.iterancestors()):
        if node.tag in _INVISIBLE or node.get("hidden") is not None:
            return False
        if _NO_DISPLAY.search(node.get("style") or ""):
            return False
    return True


def alike(first: str, second: str) -> bool:
    """Equal, or at least ``LEAD_SIMILARITY`` alike (difflib's ratio, checked cheaply first)."""
    if first == second:
        return True
    shorter, longer = sorted((len(first), len(second)))
    if shorter < longer * LEAD_SIMILARITY / (2 - LEAD_SIMILARITY):
        return False
    matcher = SequenceMatcher(None, first, second, autojunk=False)
    return matcher.quick_ratio() >= LEAD_SIMILARITY and matcher.ratio() >= LEAD_SIMILARITY
