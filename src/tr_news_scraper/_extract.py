"""An article page's headline, byline, publication time and text (internal).

What the page states in its JSON-LD, ``<h1>`` and meta tags comes first; trafilatura reads the body
and stands in for anything the page doesn't state (F3). trafilatura only ever gets HTML that
``Http`` downloaded: its own downloader is never used (F4). It's imported on first use, so
importing the package stays light (F12).
"""

from __future__ import annotations

import json
import threading
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from importlib.metadata import version
from typing import Any

from tr_news_scraper._structured import (
    choose_author,
    choose_headline,
    line,
    read_page,
    read_time,
    with_lead,
)

SETTINGS = (
    "structured data first; precision, original publication date with its offset, "
    "URL date last, no extensive date search, no comments, no sign-up boxes"
)
SIGN_UP_BOXES = ("mail-list", "maillist", "mailing-list", "abone-ol")
"""Words in a class or id, in any case, that name a sign-up box inside an article, such as Kısa
Dalga's mailing list. trafilatura already drops newsletter boxes. Broader words would catch too
much: some sites wrap the article itself in a "subscriber-content" element."""
_LOWER = 'translate({attribute}, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")'
SIGN_UP_XPATH = "//*[{}]".format(
    " or ".join(
        f'contains({_LOWER.format(attribute=attribute)}, "{word}")'
        for word in SIGN_UP_BOXES
        for attribute in ("@class", "@id")
    )
)
DATE_FORMAT = "%Y-%m-%dT%H:%M:%S%z"
MAX_PAGE_CHARACTERS = 8_000_000
"""Pages above this aren't parsed. Article pages are at most about 470,000 characters."""
ONE_PAGE_AT_A_TIME = threading.Lock()
"""Held while a page is parsed, by trafilatura and for its structured data, and while that page's
trees are freed.

trafilatura parses every page with one lxml parser, and lxml then gives every thread that uses
it the same libxml2 string dictionary, which two threads can't safely change at once. Outlet
threads reading pages together aborted the process (CI, Linux, lxml 6.1.3). Downloads still
overlap: only reading, about 20 ms a page, takes turns."""


@dataclass(frozen=True, slots=True)
class Extracted:
    """What one page says about its article, or why it couldn't be read."""

    title: str | None = None
    author: str | None = None
    published: datetime | None = None
    """The original publication time, in Europe/Istanbul, from the page's own offset. Midnight
    can mean only the day is known."""
    text: str | None = None
    """One paragraph per line."""
    error: str | None = None


def extractor() -> str:
    """trafilatura's version and fetch's settings. Records are kept under it, so a new version
    or new settings extract again."""
    return f"trafilatura {version('trafilatura')}; {SETTINGS}"


def extract(html: str, url: str, outlet_name: str = "") -> Extracted:
    """Read an article page with fetch's settings (F3, D3 as amended by SPEC-1.1 D6).

    ``outlet_name`` is the outlet's display name: a headline's trailing outlet name, and an author
    that only names the outlet, are recognized by it.
    """
    if len(html) > MAX_PAGE_CHARACTERS:
        millions = len(html) / 1_000_000
        return Extracted(error=f"the page is too large to read ({millions:.1f} million characters)")
    from trafilatura import bare_extraction

    with ONE_PAGE_AT_A_TIME:
        document: Any = bare_extraction(
            html,
            url=url,
            with_metadata=True,
            favor_precision=True,
            include_comments=False,
            prune_xpath=SIGN_UP_XPATH,
            date_extraction_params={
                "original_date": True,
                "extensive_search": False,
                "outputformat": DATE_FORMAT,
                "deferred_url_extractor": True,
            },
        )
        facts = read_page(html)
        title = author = date = body = None
        if document is not None:
            title, author = line(document.title), line(document.author)
            date, body = document.date, _paragraphs(document.text)
        del document  # frees the page's lxml trees before another thread reads a page
    found = Extracted(
        title=choose_headline(facts, title, outlet_name),
        author=choose_author(facts, author, outlet_name),
        published=facts.published or read_time(date),
        text=with_lead(body, facts.lead),
    )
    if found.text is None:
        return Extracted(found.title, found.author, found.published, error="no article text found")
    return found


def to_json(found: Extracted, fetched_at: datetime) -> bytes:
    """A record of what was extracted and when its page was downloaded."""
    record = {
        "title": found.title,
        "author": found.author,
        "published": None if found.published is None else found.published.isoformat(),
        "text": found.text,
        "fetched_at": fetched_at.isoformat(),
    }
    return json.dumps(record, ensure_ascii=False).encode()


def from_json(data: bytes) -> tuple[Extracted, datetime]:
    """The record ``to_json`` made. Raises ``ValueError`` (or ``KeyError``) if it's damaged."""
    record = json.loads(data)
    published = record["published"]
    found = Extracted(
        title=record["title"],
        author=record["author"],
        published=None if published is None else datetime.fromisoformat(published),
        text=record["text"],
    )
    return found, datetime.fromisoformat(record["fetched_at"])


def _paragraphs(text: str | None) -> str | None:
    """Spaces collapsed within each line, blank lines dropped, NFC."""
    if not text:
        return None
    lines = (" ".join(line.split()) for line in text.splitlines())
    joined = "\n".join(line for line in lines if line)
    return unicodedata.normalize("NFC", joined) or None
