"""The accuracy gate: precision and recall per keyword on 300 hand-labeled Turkish news articles.

fixtures/labeled.csv holds articles from Euronews Türkçe, TRT Haber and NTV. Claude drafted the
labels (scripts/build_labeled_set.py) and a maintainer reviewed every row on 2026-11-07. A label
says whether the article is about the hazard:

- 1 for an event, a warning or an all-clear, the aftermath and the response, or an explainer or
  science story, including a roundup in which the hazard is one of the items;
- 0 when the word is a metaphor or a name, or when the hazard is only in the photo caption of an
  unrelated article, or distant history.

Each row is matched the way search() reads an archive: the URL, plus the title when it's a real
headline. Euronews's titles describe a photo (``title_source=image_caption``), so only its URLs
are matched, as with the built-in outlet. ``slug_text`` is a reading aid for reviewers, and
``original_labels`` keeps the draft labels a reviewer changed.

The gate holds the matcher to what it can see: recall counts the articles whose URL or headline
names the hazard. Articles that never name it there (a landslide reported as "toprak kayması",
an AFAD note ruling out a tsunami after an earthquake) can only be found in the article text,
which fetch() reads, so their effect on recall is reported without a gate.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import pytest

from tr_news_scraper.matching import KeywordQuery, fold, url_slug_tokens

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
TITLE_SOURCES = {"headline", "image_caption"}
DRAFT_LABELS = re.compile(" ".join(f"{column}=[01]" for column in KEYWORDS))


@dataclass(frozen=True, slots=True)
class Score:
    true_positives: int
    false_positives: int
    missed: int  # about the hazard and naming it, but not found
    unnamed: int  # about the hazard, but the URL and headline don't name it
    misses: tuple[str, ...]

    @property
    def precision(self) -> float:
        found = self.true_positives + self.false_positives
        return self.true_positives / found if found else 1.0

    @property
    def recall(self) -> float:
        """Recall among the articles whose URL or headline names the hazard."""
        expected = self.true_positives + self.missed
        return self.true_positives / expected if expected else 1.0

    @property
    def overall_recall(self) -> float:
        """Recall among all the articles about the hazard."""
        expected = self.true_positives + self.missed + self.unnamed
        return self.true_positives / expected if expected else 1.0


@cache
def rows() -> tuple[dict[str, str], ...]:
    with LABELS.open(encoding="utf-8", newline="") as source:
        return tuple(csv.DictReader(source))


def headline(row: dict[str, str], *, titles: bool) -> str | None:
    """The title search() matches: only a real headline, never a photo caption."""
    return row["title"] if titles and row["title_source"] == "headline" else None


def names(keyword: str, url: str, title: str | None) -> bool:
    """Whether the URL or headline contains the keyword's letters at all, in any form."""
    texts = [" ".join(url_slug_tokens(url))] + ([fold(title)] if title is not None else [])
    return any(fold(keyword) in text for text in texts)


def score(column: str, *, titles: bool = True) -> Score:
    keyword = KEYWORDS[column]
    query = KeywordQuery([keyword])
    tp = fp = missed = unnamed = 0
    misses: list[str] = []
    for row in rows():
        title = headline(row, titles=titles)
        found = query.matches(title=title, url=row["url"])
        expected = row[column] == "1"
        tp += found and expected
        fp += found and not expected
        if expected and not found:
            if names(keyword, row["url"], title):
                missed += 1
                misses.append(f"missed: {row['url']}")
            else:
                unnamed += 1
        if found and not expected:
            misses.append(f"false positive: {row['url']}")
    return Score(tp, fp, missed, unnamed, tuple(misses))


@pytest.mark.parametrize("column", KEYWORDS)
def test_matching_meets_the_accuracy_gate(column: str) -> None:
    result = score(column)
    print(
        f"{column}: precision {result.precision:.3f}, recall {result.recall:.3f} "
        f"({result.overall_recall:.3f} counting articles that don't name it)"
    )
    assert result.precision >= MIN_PRECISION, result.misses
    assert result.recall >= MIN_RECALL, result.misses


def test_url_only_recall_is_reported_without_a_gate() -> None:
    for column in KEYWORDS:
        result = score(column, titles=False)
        print(f"{column}: URL-only recall {result.overall_recall:.3f}")
        assert 0.0 <= result.overall_recall <= 1.0


def test_every_keyword_has_enough_labeled_examples() -> None:
    for column in KEYWORDS:
        labels = [row[column] for row in rows()]
        assert set(labels) <= {"0", "1"}, f"{column} has undecided labels"
        assert labels.count("0") >= MIN_EXAMPLES, column
        result = score(column)
        assert result.true_positives + result.missed >= MIN_EXAMPLES, column


def test_every_row_is_reviewed_and_well_formed() -> None:
    for row in rows():
        assert row["reviewed"] == "yes", row["url"]
        assert row["title_source"] in TITLE_SOURCES, row["url"]
        if draft := row["original_labels"]:
            assert DRAFT_LABELS.fullmatch(draft), row["url"]
            current = " ".join(f"{column}={row[column]}" for column in KEYWORDS)
            assert draft != current, row["url"]
