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

from tr_news_scraper._suffixes import prefix_pattern, stem_pattern

__all__ = ["KeywordQuery", "Match", "fold", "tokens", "tr_lower"]

Field = Literal["title", "text"]
Mode = Literal["exact", "stem", "prefix"]

PREFIX_MIN_LETTERS = 5
# İ→i and I→ı before lowercasing; the modifier-letter apostrophe (U+02BC) is a Unicode letter,
# so it becomes a plain apostrophe to separate words like ' and ’ do.
_NORMALIZE = str.maketrans({"İ": "i", "I": "ı", "ʼ": "'"})
_FOLD = str.maketrans("çğıöşüâîû", "cgiosuaiu")
_WORD = re.compile(r"[^\W_]+")
_WORD_START = r"(?<![^\W_])"
_WORD_END = r"(?![^\W_])"
_WORD_GAP = r"[\W_]+"


def tr_lower(text: str) -> str:
    """Lowercase Turkish text correctly: ``'IŞIK'`` → ``'ışık'``, ``'İSTANBUL'`` → ``'istanbul'``.

    The result is NFC-normalized, and every apostrophe style separates words.
    """
    return unicodedata.normalize("NFC", text).translate(_NORMALIZE).lower()


def fold(text: str) -> str:
    """Lowercase and drop Turkish diacritics, as URL slugs do: ``'Kahramanmaraş'`` →
    ``'kahramanmaras'``."""
    return tr_lower(text).translate(_FOLD)


def tokens(text: str) -> list[str]:
    """Split text into lowercase words; apostrophes, hyphens and punctuation separate words."""
    return _WORD.findall(tr_lower(text))


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

    def find(self, normalized: str) -> str | None:
        found = self.pattern.search(normalized)
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

    def match(self, *, title: str | None = None, text: str | None = None) -> tuple[Match, ...]:
        """Every keyword found, at most once per field: titles first, then text, each in
        keyword order."""
        found: list[Match] = []
        fields: tuple[tuple[Field, str | None], ...] = (("title", title), ("text", text))
        for field, value in fields:
            if value is None:
                continue
            normalized = tr_lower(value)
            for keyword in self._keywords:
                token = keyword.find(normalized)
                if token is not None:
                    found.append(Match(keyword.text, field, token, keyword.mode))
        return tuple(found)

    def matches(self, *, title: str | None = None, text: str | None = None) -> bool:
        """Whether any keyword matches any of the given fields."""
        return bool(self.match(title=title, text=text))


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
    return _Keyword(text, mode, _compile(words, mode))


def _compile(words: list[str], mode: Mode) -> re.Pattern[str]:
    *leading, last = words
    if mode == "prefix":
        last_part = prefix_pattern(last)
    elif mode == "stem":
        last_part = stem_pattern(last) + _WORD_END
    else:
        last_part = re.escape(last) + _WORD_END
    parts = [re.escape(word) for word in leading] + [last_part]
    return re.compile(_WORD_START + _WORD_GAP.join(parts))
