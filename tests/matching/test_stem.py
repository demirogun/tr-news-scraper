"""Short keywords: the ordered Turkish suffix grammar, consonant softening, and speed."""

from __future__ import annotations

import time

import pytest

from tr_news_scraper.matching import KeywordQuery


def matches(keyword: str, title: str) -> bool:
    return KeywordQuery([keyword]).matches(title=title)


@pytest.mark.parametrize(
    ("keyword", "word"),
    [
        ("sel", "seller"),
        ("sel", "selde"),
        ("sel", "selin"),
        ("sel", "sele"),
        ("sel", "selden"),
        ("sel", "selleri"),
        ("sel", "sellerin"),
        ("sel", "sellerde"),
        ("sel", "sel"),
        ("çığ", "çığa"),
        ("çığ", "çığda"),
        ("çığ", "çığın"),
        ("çığ", "çığlar"),
        ("çığ", "çığdaki"),
        ("kaya", "kayalar"),
        ("kaya", "kayadan"),
        ("kaya", "kayası"),
        ("kaya", "kayaya"),
        ("kaya", "kayaların"),
    ],
)
def test_short_keywords_match_inflected_forms(keyword: str, word: str) -> None:
    assert matches(keyword, f"Bölgede {word} görüldü")


@pytest.mark.parametrize(
    ("keyword", "word"),
    [
        ("sel", "selam"),
        ("sel", "Selçuk"),
        ("sel", "selfie"),
        ("sel", "seçim"),
        ("sel", "kişisel"),
        ("sel", "Brüksel"),
        ("çığ", "çığlık"),
        ("çığ", "çığır"),
        ("çığ", "açığı"),
        ("kaya", "kayak"),
        ("kaya", "kaybol"),
        ("kaya", "kaymakam"),
    ],
)
def test_short_keywords_ignore_words_that_only_start_alike(keyword: str, word: str) -> None:
    assert not matches(keyword, f"Bölgede {word} görüldü")


def test_short_keywords_report_stem_mode() -> None:
    match = KeywordQuery(["sel"]).match(title="Sellerde can kaybı")[0]
    assert (match.token, match.mode) == ("sellerde", "stem")


def test_a_documented_limitation_names_that_look_inflected_still_match() -> None:
    assert matches("sel", "Yavuz Sultan Selim Köprüsü")


@pytest.mark.parametrize("word", ["obruk", "obruğu", "obruğa", "obruklar"])
def test_a_final_k_softens_before_a_vowel_in_prefix_mode(word: str) -> None:
    assert matches("obruk", f"Konya'da {word}")


@pytest.mark.parametrize(
    ("keyword", "word"), [("ağaç", "ağacı"), ("dip", "dibi"), ("renk", "rengi")]
)
def test_final_consonants_soften_in_stem_mode(keyword: str, word: str) -> None:
    assert matches(keyword, f"Bir {word} gördük")


def test_softening_only_happens_before_a_vowel() -> None:
    assert not matches("ağaç", "ağacta")


def test_phrases_use_the_stem_grammar_for_a_short_last_word() -> None:
    assert matches("ani sel", "Ani selde 3 kişi kayboldu")
    assert not matches("ani sel", "Ani selam verdi")


def test_quotes_still_force_an_exact_short_word() -> None:
    assert not matches('"sel"', "Seller sürüyor")


def test_a_very_long_token_is_matched_in_linear_time() -> None:
    query = KeywordQuery(["sel", "çığ", "deprem"])
    hostile = "sel" + "ler" * 3_000 + "x"
    started = time.perf_counter()
    query.matches(title=hostile)
    assert time.perf_counter() - started < 0.05
