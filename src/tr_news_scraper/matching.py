"""Keyword matching that understands Turkish.

``KeywordQuery`` decides whether a headline or text mentions any of the user's keywords and
explains every match::

    >>> query = KeywordQuery(["deprem", "toprak kayması"])
    >>> [m.reason for m in query.match(title="Kahramanmaraş'ta depremin ardından")]
    ["title: 'depremin' matches 'deprem' (prefix)"]

The rules:

- Turkish casing: ``tr_lower`` maps İ→i and I→ı before lowercasing, so "IŞIK" becomes "ışık"
  (Python's own ``str.lower`` gives "işik").
- A keyword of five or more letters matches any word that starts with it ("deprem" finds
  "depremin" and "depremzede"). A shorter keyword matches the word plus Turkish inflectional
  suffixes only ("sel" finds "sellerde" but not "selam"); see ``_suffixes`` for the grammar.
- ``word*`` forces prefix matching and ``"word"`` forces an exact match.
- In a phrase, the earlier words must match exactly and the last one follows the rules above.
- Apostrophes, hyphens and punctuation separate words: "Kahramanmaraş'ta" is "kahramanmaraş" + "ta".
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal
from urllib.parse import unquote, urlsplit

from tr_news_scraper._suffixes import prefix_pattern, stem_pattern

__all__ = ["KeywordQuery", "Match", "fold", "tokens", "tr_lower", "url_slug_tokens"]

Field = Literal["title", "url", "text"]
Mode = Literal["exact", "stem", "prefix"]

PREFIX_MIN_LETTERS = 5
_FOLD = str.maketrans("çğıöşüâîû", "cgiosuaiu")
_WORD = re.compile(r"[^\W_]+")
_WORD_START = r"(?<![^\W_])"
_WORD_END = r"(?![^\W_])"
_WORD_GAP = r"[\W_]+"
_PAGE_EXTENSION = re.compile(r"\.(?:html?|amp)$", re.IGNORECASE)
_TRAILING_ID = re.compile(r"-\d+$")


def tr_lower(text: str) -> str:
    """Lowercase Turkish text correctly: ``'IŞIK'`` → ``'ışık'``, ``'İSTANBUL'`` → ``'istanbul'``.

    The result is NFC-normalized, and every apostrophe style separates words.
    """
    text = unicodedata.normalize("NFC", text)
    # İ→i and I→ı before lowercasing. The modifier-letter apostrophe (U+02BC) is a Unicode
    # letter, so it becomes a plain apostrophe to separate words like ' and ’ do. Three replace
    # calls are several times faster than str.translate on non-ASCII text.
    return text.replace("İ", "i").replace("I", "ı").replace("ʼ", "'").lower()


def fold(text: str) -> str:
    """Lowercase and drop Turkish diacritics, as URL slugs do: ``'Kahramanmaraş'`` →
    ``'kahramanmaras'``."""
    return tr_lower(text).translate(_FOLD)


def tokens(text: str) -> list[str]:
    """Split text into lowercase words; apostrophes, hyphens and punctuation separate words."""
    return _WORD.findall(tr_lower(text))


def url_slug_tokens(url: str) -> list[str]:
    """The folded words of an article URL's slug.

    Only the slug counts: the last path segment, or the one before it if the last is a number.
    A page extension (``.html``, ``.htm``, ``.amp``) and a trailing ``-<id>`` are dropped, and
    category folders, the query string and the fragment are ignored.
    """
    segments = [segment for segment in unquote(urlsplit(url).path).split("/") if segment]
    if not segments:
        return []
    slug = segments[-1]
    if slug.isdigit() and len(segments) > 1:
        slug = segments[-2]
    slug = _TRAILING_ID.sub("", _PAGE_EXTENSION.sub("", slug))
    return _WORD.findall(fold(slug))


@dataclass(frozen=True, slots=True)
class Match:
    """One keyword found in one field."""

    keyword: str
    field: Field
    token: str
    mode: Mode

    @property
    def reason(self) -> str:
        """Why this matched, e.g. ``title: 'depremin' matches 'deprem' (prefix)``."""
        return f"{self.field}: {self.token!r} matches {self.keyword!r} ({self.mode})"


@dataclass(frozen=True, slots=True)
class _Keyword:
    text: str
    mode: Mode
    pattern: re.Pattern[str]
    folded_pattern: re.Pattern[str]
    # Text that every match contains; a plain substring test rules most texts out before the
    # regex runs.
    literal: str
    folded_literal: str

    def find(self, normalized: str, *, folded: bool) -> str | None:
        if folded:
            literal, pattern = self.folded_literal, self.folded_pattern
        else:
            literal, pattern = self.literal, self.pattern
        if literal not in normalized:
            return None
        found = pattern.search(normalized)
        return found.group(0) if found else None


class KeywordQuery:
    """A set of keywords, any of which may match."""

    def __init__(self, keywords: Iterable[str]) -> None:
        self._keywords = tuple(_parse(keyword) for keyword in keywords)
        if not self._keywords:
            raise ValueError("at least one keyword is needed")

    @property
    def keywords(self) -> tuple[str, ...]:
        """The keywords as written, minus surrounding spaces."""
        return tuple(keyword.text for keyword in self._keywords)

    def match(
        self, *, title: str | None = None, url: str | None = None, text: str | None = None
    ) -> tuple[Match, ...]:
        """Every keyword found, at most once per field: title, then URL slug, then text, each
        in keyword order. URL slugs are compared in folded (ASCII) form."""
        found: list[Match] = []
        fields: tuple[tuple[Field, str | None], ...] = (
            ("title", title),
            ("url", url),
            ("text", text),
        )
        for field, value in fields:
            if value is None:
                continue
            folded = field == "url"
            normalized = " ".join(url_slug_tokens(value)) if folded else tr_lower(value)
            for keyword in self._keywords:
                token = keyword.find(normalized, folded=folded)
                if token is not None:
                    found.append(Match(keyword.text, field, token, keyword.mode))
        return tuple(found)

    def matches(
        self, *, title: str | None = None, url: str | None = None, text: str | None = None
    ) -> bool:
        """Whether any keyword matches any of the given fields."""
        return bool(self.match(title=title, url=url, text=text))


def _parse(raw: str) -> _Keyword:
    text = raw.strip()
    body = text
    forced: Mode | None = None
    if len(body) >= 2 and body[0] == body[-1] == '"':
        body, forced = body[1:-1], "exact"
    elif body.endswith("*"):
        body, forced = body[:-1], "prefix"
    words = tokens(body)
    if not words:
        raise ValueError(f"keyword {raw!r} is blank")
    if len(words) == 1 and len(words[0]) < 2:
        raise ValueError(f"keyword {raw!r} is too short; use at least two letters")
    mode: Mode = forced or ("prefix" if len(words[-1]) >= PREFIX_MIN_LETTERS else "stem")
    source = _source(words, mode)
    # Every match starts with the first word, except that consonant softening may change its
    # last letter (kitap → kitabı).
    literal = words[0][:-1]
    # Folding only maps Turkish letters to ASCII; it never touches the regex syntax.
    return _Keyword(
        text,
        mode,
        re.compile(source),
        re.compile(source.translate(_FOLD)),
        literal,
        literal.translate(_FOLD),
    )


def _source(words: list[str], mode: Mode) -> str:
    *leading, last = words
    if mode == "prefix":
        last_part = prefix_pattern(last)
    elif mode == "stem":
        last_part = stem_pattern(last) + _WORD_END
    else:
        last_part = re.escape(last) + _WORD_END
    parts = [re.escape(word) for word in leading] + [last_part]
    return _WORD_START + _WORD_GAP.join(parts)
