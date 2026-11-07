"""The accuracy gate: precision and recall per keyword on real, labeled Turkish headlines.

The labels in fixtures/labeled.csv were drafted by Claude (built with
scripts/build_labeled_set.py) and are marked ``reviewed=no`` until a maintainer has checked every
row. Until then the gate guards against regressions; after the review it is authoritative.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import pytest

from tr_news_scraper.matching import KeywordQuery

LABELS = Path(__file__).parent / "fixtures" / "labeled.csv"
KEYWORDS = {
    "deprem": "deprem",
    "sel": "sel",
    "heyelan": "heyelan",
    "cig": "çığ",
    "tsunami": "tsunami",
}
MIN_PRECISION = 0.95
MIN_RECALL = 0.90
MIN_EXAMPLES = 20


@dataclass(frozen=True, slots=True)
class Score:
    true_positives: int
    false_positives: int
    false_negatives: int
    misses: tuple[str, ...]

    @property
    def precision(self) -> float:
        found = self.true_positives + self.false_positives
        return self.true_positives / found if found else 1.0

    @property
    def recall(self) -> float:
        expected = self.true_positives + self.false_negatives
        return self.true_positives / expected if expected else 1.0


@cache
def rows() -> tuple[dict[str, str], ...]:
    with LABELS.open(encoding="utf-8", newline="") as source:
        return tuple(csv.DictReader(source))


def score(column: str, *, field: str) -> Score:
    query = KeywordQuery([KEYWORDS[column]])
    tp = fp = fn = 0
    misses: list[str] = []
    for row in rows():
        found = bool(
            query.match(title=row["title"]) if field == "title" else query.match(url=row["url"])
        )
        expected = row[column] == "1"
        tp += found and expected
        fp += found and not expected
        fn += expected and not found
        if found != expected:
            misses.append(f"{'false positive' if found else 'missed'}: {row['title']}")
    return Score(tp, fp, fn, tuple(misses))


@pytest.mark.parametrize("column", KEYWORDS)
def test_title_matching_meets_the_accuracy_gate(column: str) -> None:
    result = score(column, field="title")
    print(f"{column}: precision {result.precision:.3f}, recall {result.recall:.3f}")
    assert result.precision >= MIN_PRECISION, result.misses
    assert result.recall >= MIN_RECALL, result.misses


def test_url_only_recall_is_reported_without_a_gate() -> None:
    for column in KEYWORDS:
        result = score(column, field="url")
        print(f"{column}: URL-only recall {result.recall:.3f}")
        assert 0.0 <= result.recall <= 1.0


def test_every_keyword_has_enough_labeled_examples() -> None:
    for column in KEYWORDS:
        labels = [row[column] for row in rows()]
        assert set(labels) <= {"0", "1"}, f"{column} has undecided labels"
        assert labels.count("1") >= MIN_EXAMPLES, column
        assert labels.count("0") >= MIN_EXAMPLES, column


@pytest.mark.xfail(strict=True, reason="H1: a maintainer hasn't reviewed Claude's draft labels yet")
def test_every_label_has_been_reviewed_by_a_maintainer() -> None:
    assert all(row["reviewed"] == "yes" for row in rows())
