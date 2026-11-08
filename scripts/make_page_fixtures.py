"""Turn a real article page into a test fixture that holds neither its article text nor bylines.

fetch's tests need each outlet's real page structure and metadata, but this repository must not
publish copyrighted article text or journalists' names. The skeleton keeps the structure, the
headline and the dates. It replaces:

- every text in a paragraph, list item, caption, quote, table cell or subheading, every other
  body text of three or more words, every long ``alt`` or ``title`` attribute, every
  description, and every JSON-LD body or description with filler words of the same length.
  Texts of eight or more words include "deprem". Only letters make words, so dates and times
  stay, and so does text inside elements named for times, dates, authors or sources: that's
  metadata, not article text;
- each name given with ``--author`` with the fictional name after its ``=``, wherever it appears.

It removes scripts other than JSON-LD, styles, iframes, SVG, comments and noscript blocks, keeps
only the canonical link, and declares UTF-8. The input is a page saved as UTF-8 text. Usage::

    uv run python scripts/make_page_fixtures.py page.html out.html --author "Real Name=Ayşe Demir"
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import lxml.html
from lxml import etree

FILLER = (
    "örnek",
    "metin",
    "yer",
    "tutucu",
    "cümle",
    "paragraf",
    "sayfa",
    "satır",
    "kelime",
    "deneme",
    "içerik",
    "bölüm",
)
KEYWORD = "deprem"
MIN_WORDS = 3
KEYWORD_FROM = 8
# The headline, times, and the JSON-LD scripts already handled keep their own text.
KEPT_TAGS = frozenset({"h1", "time", "title", "script"})
CONTENT_TAGS = frozenset(
    {"p", "li", "blockquote", "q", "figcaption", "h2", "h3", "h4", "h5", "h6", "td", "th", "pre"}
)
REMOVED_TAGS = ("style", "noscript", "iframe", "svg", "template", "object", "embed")
JSON_TEXT_FIELDS = frozenset({"articleBody", "description", "text", "abstract", "caption"})
DESCRIPTIONS = frozenset({"description", "og:description", "twitter:description"})
TEXT_ATTRIBUTES = ("alt", "title", "aria-label")
# Python's upper() turns "i" into "I"; Turkish needs "İ" (and "I" for dotless "ı").
_TURKISH_UPPER = {"i": "İ", "ı": "I"}
_WORDS = re.compile(r"[^\W\d_]+")
_METADATA = re.compile(r"time|date|author|byline|writer|source|editor", re.IGNORECASE)
_JSON_TEXT = re.compile(
    r'("(?:articleBody|description|text|abstract|caption)"\s*:\s*")((?:[^"\\]|\\.)*)(")'
)


class Skeleton:
    """Builds the skeleton of one page; ``seed`` keeps the filler deterministic."""

    def __init__(self, authors: dict[str, str]) -> None:
        self.authors = authors
        self.seed = 0

    def filler(self, words: int) -> str:
        chosen = [FILLER[(self.seed + i) % len(FILLER)] for i in range(words)]
        self.seed += words
        if words >= KEYWORD_FROM:
            chosen[1] = KEYWORD
        text = " ".join(chosen)
        return f"{_TURKISH_UPPER.get(text[:1], text[:1].upper())}{text[1:]}."

    def replace_long(self, text: str | None, minimum: int = MIN_WORDS) -> str | None:
        """Filler for a text of ``minimum`` or more words; anything shorter is kept."""
        if text is None:
            return None
        words = len(_WORDS.findall(text))
        return self.filler(words) if words >= minimum else text

    def rename(self, text: str) -> str:
        for real, fictional in self.authors.items():
            text = text.replace(real, fictional)
        return text

    def json_ld(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: self.replace_long(item)
                if key in JSON_TEXT_FIELDS and isinstance(item, str)
                else self.json_ld(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self.json_ld(item) for item in value]
        return value

    def build(self, html: str) -> str:
        root = lxml.html.document_fromstring(html)
        self._strip(root)
        head = root.find("head")
        if head is not None:
            self._metadata(head)
        body = root.find("body")
        if body is not None:
            self._body(body)
        self._rename_everywhere(root)
        markup = lxml.html.tostring(root, encoding="unicode", doctype="<!DOCTYPE html>")
        return f"{markup}\n"

    def _strip(self, root: lxml.html.HtmlElement) -> None:
        etree.strip_elements(root, etree.Comment, etree.ProcessingInstruction, with_tail=False)
        for element in list(root.iter("script")):
            if (element.get("type") or "").lower() == "application/ld+json":
                element.text = self._json_ld_text(element.text or "")
            else:
                _drop(element)
        for tag in REMOVED_TAGS:
            for element in list(root.iter(tag)):
                _drop(element)
        for link in list(root.iter("link")):
            if (link.get("rel") or "").lower() != "canonical":
                _drop(link)
        for meta in list(root.iter("meta")):
            if meta.get("charset") is not None or (meta.get("http-equiv") or "").lower() == (
                "content-type"
            ):
                _drop(meta)

    def _json_ld_text(self, text: str) -> str:
        """JSON-LD with its text fields replaced. Sites often publish JSON-LD that isn't strict
        JSON, and readers like trafilatura accept it, so malformed JSON-LD is edited in place
        instead of being dropped."""
        try:
            data = json.loads(text)
        except ValueError:
            return _JSON_TEXT.sub(
                lambda m: f"{m.group(1)}{self.replace_long(m.group(2))}{m.group(3)}", text
            )
        return json.dumps(self.json_ld(data), ensure_ascii=False)

    def _metadata(self, head: lxml.html.HtmlElement) -> None:
        head.insert(0, lxml.html.Element("meta", charset="utf-8"))
        for meta in head.iter("meta"):
            name = (meta.get("name") or meta.get("property") or "").lower()
            if name in DESCRIPTIONS:
                meta.set("content", self.replace_long(meta.get("content")) or "")

    def _body(self, body: lxml.html.HtmlElement) -> None:
        for element in body.iter():
            if not isinstance(element.tag, str):
                continue
            ancestors = {a.tag for a in element.iterancestors() if isinstance(a.tag, str)}
            if any(_is_metadata(node) for node in (element, *element.iterancestors())):
                continue
            # Inside article content every word goes; elsewhere, such as menus, short labels stay.
            inner = 1 if ({element.tag} | ancestors) & CONTENT_TAGS else MIN_WORDS
            outer = 1 if ancestors & CONTENT_TAGS else MIN_WORDS
            if element.tag not in KEPT_TAGS and not ancestors & KEPT_TAGS:
                element.text = self.replace_long(element.text, inner)
                for attribute in TEXT_ATTRIBUTES:
                    if element.get(attribute) is not None:
                        element.set(attribute, self.replace_long(element.get(attribute)) or "")
            if not ancestors & KEPT_TAGS:
                element.tail = self.replace_long(element.tail, outer)

    def _rename_everywhere(self, root: lxml.html.HtmlElement) -> None:
        for element in root.iter():
            if not isinstance(element.tag, str):
                continue
            if element.text:
                element.text = self.rename(element.text)
            if element.tail:
                element.tail = self.rename(element.tail)
            for attribute, value in element.attrib.items():
                element.set(attribute, self.rename(value))


def _is_metadata(element: lxml.html.HtmlElement) -> bool:
    """Whether an element is named for a time, date, author or source."""
    if not isinstance(element.tag, str):
        return False
    return bool(_METADATA.search(f"{element.get('class') or ''} {element.get('id') or ''}"))


def _drop(element: lxml.html.HtmlElement) -> None:
    """Remove an element but keep its tail text in place."""
    element.drop_tree()


def parse_authors(pairs: Iterable[str]) -> dict[str, str]:
    authors = {}
    for pair in pairs:
        real, separator, fictional = pair.partition("=")
        if not separator or not real or not fictional:
            raise SystemExit(f"--author needs 'Real Name=Fictional Name', not {pair!r}")
        authors[real] = fictional
    return authors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("page", type=Path, help="the page, saved as UTF-8 text")
    parser.add_argument("output", type=Path)
    parser.add_argument("--author", action="append", default=[], help="Real Name=Fictional Name")
    arguments = parser.parse_args()
    skeleton = Skeleton(parse_authors(arguments.author))
    html = arguments.page.read_text(encoding="utf-8")
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(skeleton.build(html), encoding="utf-8", newline="\n")
    print(f"{arguments.page.name}: {len(html):,} → {arguments.output.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
