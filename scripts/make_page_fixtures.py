"""Turn a real article page into a test fixture that holds neither its article text nor bylines.

fetch's tests need each outlet's real page structure and metadata, but this repository must not
publish copyrighted article text or journalists' names. The skeleton keeps the structure, the
headline and the dates. It replaces:

- every text in a paragraph, list item, caption, quote, table cell or subheading, every other
  body text of three or more words, every long ``alt`` or ``title`` attribute, every
  description, and every JSON-LD body or description with filler words of the same length.
  Equal texts get equal filler, so a lead that repeats the page's description still does.
  Texts of eight or more words include "deprem". Only letters make words, so dates and times
  stay, and so does text inside elements named for times, dates, authors or sources: that's
  metadata, not article text;
- every person named as an author in JSON-LD or a ``meta[name=author]`` tag, and each name given
  with ``--author``, with a fictional name, wherever and however it's spelled: as written, in
  capitals, in title case and as a URL slug. Organizations, desks and agencies keep their names.

It removes scripts other than JSON-LD, styles, iframes, SVG, comments and noscript blocks, keeps
only the canonical link, and declares UTF-8. The input is a page saved as UTF-8 text. Usage::

    uv run python scripts/make_page_fixtures.py page.html out.html --author "Real Name=Ayşe Demir"
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

import lxml.html
from lxml import etree

from tr_news_scraper.matching import fold, tr_lower

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
FICTIONAL_NAMES = (
    "Ayşe Demir",
    "Deniz Yılmaz",
    "Elif Kaya",
    "Can Öztürk",
    "Zeynep Arslan",
    "Mert Çelik",
    "Selin Aydın",
    "Burak Şahin",
)
"""Fictional names for bylines that ``--author`` doesn't cover, used in this order."""
# Words (folded) that mark a byline as a desk, an agency or an outlet rather than a person.
DESK_WORDS = frozenset(
    {
        *("haber", "haberler", "haberleri", "ajans", "ajansi", "merkez", "merkezi"),
        *("servis", "servisi", "gazete", "gazetesi", "editor", "editoru", "masasi"),
        *("desk", "medya", "news", "staff"),
    }
)
AGENCIES = frozenset({"aa", "iha", "dha", "anka", "afp", "ap", "dpa", "reuters", "sputnik", "bbc"})
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
_JSON_AUTHOR = re.compile(r'"author"\s*:\s*(\{[^{}]*\}|\[[^\[\]]*\]|"(?:[^"\\]|\\.)*")')
_JSON_NAME = re.compile(r'"name"\s*:\s*"((?:[^"\\]|\\.)*)"')
_EMAIL = re.compile(r"[^\s/,;|()<>]+@[^\s/,;|()<>]+")
_NAME_EDGES = " /,;|-–—·()<>"


class Skeleton:
    """Builds the skeleton of one page; ``seed`` keeps the filler deterministic."""

    def __init__(self, authors: dict[str, str]) -> None:
        self.authors = dict(authors)
        self.seed = 0
        self._fillers: dict[str, str] = {}
        for real, fictional in authors.items():
            self._add_spellings(real, fictional)

    def filler(self, words: int) -> str:
        chosen = [FILLER[(self.seed + i) % len(FILLER)] for i in range(words)]
        self.seed += words
        if words >= KEYWORD_FROM:
            chosen[1] = KEYWORD
        text = " ".join(chosen)
        return f"{_TURKISH_UPPER.get(text[:1], text[:1].upper())}{text[1:]}."

    def replace_long(self, text: str | None, minimum: int = MIN_WORDS) -> str | None:
        """Filler for a text of ``minimum`` or more words; anything shorter is kept. The same
        text, with its spaces collapsed and NFC, always gets the same filler."""
        if text is None:
            return None
        words = len(_WORDS.findall(text))
        if words < minimum:
            return text
        key = unicodedata.normalize("NFC", " ".join(text.split()))
        if key not in self._fillers:
            self._fillers[key] = self.filler(words)
        return self._fillers[key]

    def rename(self, text: str) -> str:
        for real, fictional in self.authors.items():
            text = text.replace(real, fictional)
        return text

    def add_byline(self, name: str) -> None:
        """Give a person named as an author a fictional name, in every spelling (see above)."""
        person = " ".join(_EMAIL.sub(" ", name).split()).strip(_NAME_EDGES)
        if not person or _is_desk(person):
            return
        known = {fold(real): fictional for real, fictional in self.authors.items()}
        self._add_spellings(person, known.get(fold(person)) or self._unused_name())

    def _add_spellings(self, real: str, fictional: str) -> None:
        """Map ``real`` as written, in capitals, in title case and as a URL slug, unless a
        spelling is mapped already."""
        variants = {
            real: _same_case(real, fictional),
            tr_upper(real): tr_upper(fictional),
            tr_title(real): tr_title(fictional),
            _slug(real): _slug(fictional),
        }
        for spelling, replacement in variants.items():
            if spelling:
                self.authors.setdefault(spelling, replacement)

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

    def _unused_name(self) -> str:
        taken = {fold(name) for name in self.authors.values()}
        for name in FICTIONAL_NAMES:
            if fold(name) not in taken:
                return name
        raise SystemExit("too many bylines on one page: add names to FICTIONAL_NAMES")

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
        """JSON-LD with its text fields replaced and its bylines registered. Sites often publish
        JSON-LD that isn't strict JSON, and readers like trafilatura accept it, so malformed
        JSON-LD is edited in place instead of being dropped."""
        try:
            data = json.loads(text)
        except ValueError:
            for found in _JSON_AUTHOR.finditer(text):
                value = found.group(1)
                names = _JSON_NAME.findall(value) if value[:1] in "{[" else [value.strip('"')]
                for name in names:
                    self.add_byline(name)
            return _JSON_TEXT.sub(
                lambda m: f"{m.group(1)}{self.replace_long(m.group(2))}{m.group(3)}", text
            )
        for name in _authors(data):
            self.add_byline(name)
        return json.dumps(self.json_ld(data), ensure_ascii=False)

    def _metadata(self, head: lxml.html.HtmlElement) -> None:
        head.insert(0, lxml.html.Element("meta", charset="utf-8"))
        for meta in head.iter("meta"):
            name = (meta.get("name") or meta.get("property") or "").lower()
            if name in DESCRIPTIONS:
                meta.set("content", self.replace_long(meta.get("content")) or "")
            elif name == "author" and meta.get("content"):
                self.add_byline(meta.get("content") or "")

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


def tr_upper(text: str) -> str:
    """Turkish capitals: ``"Şişli"`` → ``"ŞİŞLİ"``."""
    return "".join(_TURKISH_UPPER.get(letter, letter.upper()) for letter in text)


def tr_title(text: str) -> str:
    """Turkish title case: ``"AYŞE DEMİR"`` → ``"Ayşe Demir"``."""
    return " ".join(tr_upper(word[:1]) + tr_lower(word[1:]) for word in text.split())


def _same_case(model: str, name: str) -> str:
    return tr_upper(name) if model == tr_upper(model) else name


def _slug(name: str) -> str:
    return "-".join(fold(name).split())


def _is_desk(name: str) -> bool:
    """Whether a byline names a desk, an agency or an outlet rather than a person: one word,
    a known agency, or a word like "haber" or "ajans"."""
    words = set(fold(name).split())
    return len(words) < 2 or bool(words & AGENCIES) or bool(words & DESK_WORDS)


def _authors(data: Any) -> Iterator[str]:
    """The names of the people every ``author`` in JSON-LD data names; organizations are left
    out."""
    if isinstance(data, list):
        for item in data:
            yield from _authors(item)
    elif isinstance(data, dict):
        for key, value in data.items():
            if key == "author":
                yield from _person_names(value)
            else:
                yield from _authors(value)


def _person_names(value: Any) -> Iterable[str]:
    for item in value if isinstance(value, list) else [value]:
        if isinstance(item, str):
            yield item
        elif isinstance(item, dict) and isinstance(item.get("name"), str):
            kinds = item.get("@type")
            kinds = [kinds] if isinstance(kinds, str) else kinds if isinstance(kinds, list) else []
            if not any(str(kind).endswith("Organization") for kind in kinds):
                yield item["name"]


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
    renamed = sorted(
        real for real in skeleton.authors if real not in parse_authors(arguments.author)
    )
    if renamed:
        print(f"bylines given fictional names: {len(renamed)} spellings")


if __name__ == "__main__":
    main()
