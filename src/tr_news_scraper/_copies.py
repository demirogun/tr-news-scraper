"""Copies of one story among fetched articles (F7, D4) (internal).

Two articles are copies when at least 80% of the shorter text's 8-word phrases appear in the
other text, the shorter text has at least 30 words, and, when both are dated, they were published
at most 3 days apart. Copies of copies share one group. Nothing is removed: the groups only mark
the copies, so counts can be corrected without deciding for the researcher.

Phrases are fingerprinted with a stable hash, so the groups are the same on every run. One phrase
in four builds the index of candidate pairs, leaving out phrases found in more than 50 articles
(page furniture and boilerplate); every candidate pair is then checked on all of its phrases.
"""

from __future__ import annotations

import zlib
from collections import Counter, defaultdict
from collections.abc import Sequence
from datetime import date

from tr_news_scraper.matching import tokens

PHRASE_WORDS = 8
MIN_WORDS = 30
MIN_SHARED = 0.8
MAX_DAYS_APART = 3
BOILERPLATE_ARTICLES = 50
SAMPLE = 4
CANDIDATE_SHARED = 0.5
"""How much of the shorter text's sampled phrases a pair must share to be checked in full."""


def phrases(text: str) -> frozenset[int]:
    """Stable fingerprints of a text's 8-word phrases, ignoring case and punctuation."""
    return frozenset(_fingerprints(tokens(text)))


def copy_groups(texts: Sequence[str | None], days: Sequence[date | None]) -> list[int | None]:
    """A group number for every article that has a copy, from 1 in table order; ``None`` for
    a story found once."""
    # Only the sampled fingerprints stay in memory; a candidate's full set is made when needed.
    eligible: dict[int, str] = {}
    sampled: dict[int, set[int]] = {}
    for i, text in enumerate(texts):
        found = tokens(text) if text else []
        if text and len(found) >= MIN_WORDS:
            eligible[i] = text
            sampled[i] = {h for h in _fingerprints(found) if h % SAMPLE == 0}
    spread = Counter(h for found in sampled.values() for h in found)
    index: dict[int, list[int]] = defaultdict(list)
    for i in eligible:
        for h in sampled[i]:
            if 1 < spread[h] <= BOILERPLATE_ARTICLES:
                index[h].append(i)

    parent = list(range(len(texts)))
    full: dict[int, frozenset[int]] = {}
    for i in eligible:
        shared: Counter[int] = Counter()
        for h in sampled[i]:
            for j in index.get(h, ()):
                if j > i:
                    shared[j] += 1
        for j, count in shared.items():
            smaller = min(len(sampled[i]), len(sampled[j]))
            if count < CANDIDATE_SHARED * smaller or not _close_in_time(days[i], days[j]):
                continue
            first = full[i] if i in full else full.setdefault(i, phrases(eligible[i]))
            second = full[j] if j in full else full.setdefault(j, phrases(eligible[j]))
            if len(first & second) >= MIN_SHARED * min(len(first), len(second)):
                parent[_root(parent, j)] = _root(parent, i)

    sizes = Counter(_root(parent, i) for i in range(len(texts)))
    numbers: dict[int, int] = {}
    groups: list[int | None] = []
    for i in range(len(texts)):
        root = _root(parent, i)
        if sizes[root] < 2:
            groups.append(None)
            continue
        groups.append(numbers.setdefault(root, len(numbers) + 1))
    return groups


def _fingerprints(words: Sequence[str]) -> list[int]:
    """A 64-bit fingerprint of each 8-word phrase: crc32 and adler32 of its UTF-8 text."""
    found = []
    for start in range(len(words) - PHRASE_WORDS + 1):
        phrase = " ".join(words[start : start + PHRASE_WORDS]).encode()
        found.append(zlib.crc32(phrase) << 32 | zlib.adler32(phrase))
    return found


def _close_in_time(first: date | None, second: date | None) -> bool:
    if first is None or second is None:
        return True
    return abs((first - second).days) <= MAX_DAYS_APART


def _root(parent: list[int], item: int) -> int:
    while parent[item] != item:
        parent[item] = parent[parent[item]]
        item = parent[item]
    return item
