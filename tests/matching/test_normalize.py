"""Turkish-aware normalization: casing, folding and splitting into words."""

from __future__ import annotations

import unicodedata

import pytest

from tr_news_scraper.matching import fold, tokens, tr_lower


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("IŞIK", "ışık"),
        ("İSTANBUL", "istanbul"),
        ("DİYARBAKIR", "diyarbakır"),
        ("Iğdır", "ığdır"),
        ("ÇAĞLAYAN ŞÜKRÜ ÖZÜ", "çağlayan şükrü özü"),
        ("deprem", "deprem"),
    ],
)
def test_tr_lower_follows_turkish_casing(text: str, expected: str) -> None:
    assert tr_lower(text) == expected


@pytest.mark.parametrize("text", ["İSTANBUL", "Şırnak", "Iğdır", "ÇIĞ"])
def test_decomposed_input_gives_the_same_result(text: str) -> None:
    assert tr_lower(unicodedata.normalize("NFD", text)) == tr_lower(text)


def test_tr_lower_returns_composed_text() -> None:
    assert tr_lower(unicodedata.normalize("NFD", "Şırnak")) == unicodedata.normalize(
        "NFC", "şırnak"
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Kahramanmaraş", "kahramanmaras"),
        ("ÇIĞ", "cig"),
        ("Gümüşhane", "gumushane"),
        ("Âşık Veysel", "asik veysel"),
    ],
)
def test_fold_lowercases_and_drops_diacritics_like_url_slugs(text: str, expected: str) -> None:
    assert fold(text) == expected


def test_tokens_split_on_apostrophes_and_punctuation() -> None:
    assert tokens("Kahramanmaraş'ta deprem!") == ["kahramanmaraş", "ta", "deprem"]


@pytest.mark.parametrize("apostrophe", ["'", "’", "ʼ"])
def test_every_apostrophe_style_splits_a_word(apostrophe: str) -> None:
    assert tokens(f"Van{apostrophe}da çığ") == ["van", "da", "çığ"]


def test_tokens_keep_digits_and_split_hyphens() -> None:
    assert tokens("6 Şubat 2023 deprem-tsunami") == ["6", "şubat", "2023", "deprem", "tsunami"]


def test_tokens_of_empty_text_is_empty() -> None:
    assert tokens("  — ") == []
