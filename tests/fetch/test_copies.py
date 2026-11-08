"""Copies of one story (F7, D4): at least 80% of the shorter text's 8-word phrases appear in the
other, the shorter has 30+ words, and dated copies are at most 3 days apart."""

from __future__ import annotations

import random
import time
from datetime import date, timedelta

import pytest

from tr_news_scraper._copies import copy_groups, phrases

DAY = date(2023, 2, 10)


def story(name: str, words: int) -> str:
    """A text whose words are unique to ``name``, so different stories share no phrases."""
    return " ".join(f"{name}{n}" for n in range(words)) + "."


def test_an_exact_copy_in_another_outlet_shares_a_group() -> None:
    text = story("ajans", 120)
    assert copy_groups([text, story("baska", 120), text], [DAY, DAY, DAY]) == [1, None, 1]


def test_a_shortened_wire_copy_is_still_a_copy() -> None:
    full = story("ajans", 150)
    short = " ".join(full.split()[:50])
    assert copy_groups([full, short], [DAY, DAY]) == [1, 1]


def test_another_story_on_the_same_topic_is_not_a_copy() -> None:
    shared = story("ortak", 12)
    first = f"{story('bir', 100)} {shared}"
    second = f"{story('iki', 100)} {shared}"
    assert copy_groups([first, second], [DAY, DAY]) == [None, None]


def test_an_article_reusing_two_thirds_of_another_is_not_a_copy() -> None:
    original = story("ajans", 100).split()
    reworked = " ".join(original[:70]) + " " + story("yerel", 30)
    assert copy_groups([" ".join(original), reworked], [DAY, DAY]) == [None, None]


def test_texts_under_thirty_words_are_not_compared() -> None:
    text = story("kisa", 29)
    assert copy_groups([text, text], [DAY, DAY]) == [None, None]
    longer = story("yeterli", 30)
    assert copy_groups([longer, longer], [DAY, DAY]) == [1, 1]


def test_dated_copies_must_be_published_within_three_days() -> None:
    text = story("ajans", 80)
    later = DAY + timedelta(days=3)
    much_later = DAY + timedelta(days=4)
    assert copy_groups([text, text], [DAY, later]) == [1, 1]
    assert copy_groups([text, text], [DAY, much_later]) == [None, None]
    assert copy_groups([text, text], [DAY, None]) == [1, 1]


def test_boilerplate_shared_by_many_articles_doesnt_make_them_copies() -> None:
    footer = story("altbilgi", 40)
    texts = [f"{story(f'haber{n}x', 5)} {footer}" for n in range(60)]
    assert copy_groups(texts, [DAY] * 60) == [None] * 60


def test_copies_of_copies_share_one_group_numbered_in_table_order() -> None:
    first, second = story("bir", 90), story("iki", 90)
    texts = [None, second, first, second, " ".join(first.split()[:60]), first]
    groups = copy_groups(texts, [DAY] * len(texts))
    assert groups == [None, 1, 2, 1, 2, 2]


def test_two_partial_copies_of_one_story_join_its_group_though_they_share_nothing() -> None:
    full = story("ajans", 120).split()
    first_half, second_half = " ".join(full[:60]), " ".join(full[60:])
    texts = [first_half, second_half, " ".join(full)]
    assert copy_groups(texts, [DAY, DAY, DAY]) == [1, 1, 1]


def test_phrases_ignore_case_and_punctuation_and_are_stable() -> None:
    assert phrases("Bir iki üç dört beş altı yedi sekiz.") == phrases(
        "BİR, iki üç dört; beş altı yedi sekiz"
    )
    assert phrases("bir iki üç dört beş altı yedi sekiz") == {1755898124163551673}
    assert phrases("çok kısa") == frozenset()


# Like the other speed budgets, this runs with coverage paused.
@pytest.mark.no_cover
def test_a_month_of_articles_is_grouped_in_under_ten_seconds() -> None:
    rng = random.Random(7)  # noqa: S311 - test data, not security
    vocabulary = [f"kelime{n}" for n in range(5_000)]
    texts: list[str | None] = []
    for n in range(7_600):
        if n % 10 == 9:  # every tenth article copies the one before
            texts.append(texts[-1])
        else:
            texts.append(" ".join(rng.choice(vocabulary) for _ in range(250)))
    days = [DAY + timedelta(days=n % 28) for n in range(7_600)]
    started = time.perf_counter()
    groups = copy_groups(texts, days)
    elapsed = time.perf_counter() - started
    assert sum(1 for group in groups if group is not None) >= 1_500
    assert elapsed < 10, f"took {elapsed:.1f} s"
