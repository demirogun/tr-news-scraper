"""KeywordQuery on titles and text: syntax, prefix and exact modes, phrases, reasons."""

from __future__ import annotations

import pytest

from tr_news_scraper.matching import KeywordQuery, Match


def first(query: KeywordQuery, title: str) -> Match:
    found = query.match(title=title)
    assert found, f"no match in {title!r}"
    return found[0]


@pytest.mark.parametrize(
    "title", ["Depremin ardından", "DEPREM", "depremzede aileler", "Depremlerde"]
)
def test_long_keywords_match_any_word_that_starts_with_them(title: str) -> None:
    assert first(KeywordQuery(["deprem"]), title).mode == "prefix"


def test_a_long_keyword_does_not_match_inside_a_word() -> None:
    assert not KeywordQuery(["deprem"]).matches(title="Antidepremli bina")


def test_a_trailing_star_forces_prefix_mode() -> None:
    match = first(KeywordQuery(["afet*"]), "Afetzedeler için kampanya")
    assert (match.keyword, match.token, match.mode) == ("afet*", "afetzedeler", "prefix")


def test_quotes_force_exact_mode() -> None:
    query = KeywordQuery(['"deprem"'])
    assert query.matches(title="Büyük deprem")
    assert not query.matches(title="Depremin ardından")
    assert first(query, "Büyük deprem").mode == "exact"


def test_a_phrase_matches_consecutive_words_with_the_last_one_in_prefix_mode() -> None:
    match = first(KeywordQuery(["toprak kayması"]), "Rize'de toprak kaymasında 3 ev yıkıldı")
    assert (match.token, match.mode) == ("toprak kaymasında", "prefix")


def test_a_phrase_needs_its_words_in_order_and_together() -> None:
    query = KeywordQuery(["toprak kayması"])
    assert not query.matches(title="Kayması beklenen toprak")
    assert not query.matches(title="toprak ve kayması")


def test_any_keyword_may_match() -> None:
    query = KeywordQuery(["heyelan", "deprem"])
    assert [m.keyword for m in query.match(title="Deprem sonrası heyelan")] == ["heyelan", "deprem"]


def test_turkish_casing_is_respected_in_keywords_too() -> None:
    assert KeywordQuery(["IĞDIR"]).matches(title="Iğdır'da sel")
    assert not KeywordQuery(["IĞDIR"]).matches(title="iğdir")


def test_text_is_matched_like_titles() -> None:
    match = KeywordQuery(["tsunami"]).match(text="Kıyıda tsunami uyarısı yapıldı.")[0]
    assert (match.field, match.token) == ("text", "tsunami")


def test_titles_come_before_text_and_each_keyword_matches_once_per_field() -> None:
    query = KeywordQuery(["deprem"])
    found = query.match(title="Deprem ve deprem", text="Depremin etkileri")
    assert [(m.field, m.token) for m in found] == [("title", "deprem"), ("text", "depremin")]


def test_every_match_explains_itself() -> None:
    match = first(KeywordQuery(["deprem"]), "Depremin ardından")
    assert match.reason == "title: 'depremin' matches 'deprem' (prefix)"


def test_no_fields_means_no_matches() -> None:
    assert KeywordQuery(["deprem"]).match() == ()


@pytest.mark.parametrize("keywords", [[], [""], ["   "], ["d"], ['""'], ["*"]])
def test_unusable_keywords_are_rejected(keywords: list[str]) -> None:
    with pytest.raises(ValueError, match="keyword"):
        KeywordQuery(keywords)


def test_the_query_remembers_keywords_as_written() -> None:
    assert KeywordQuery([" Deprem ", '"sel"']).keywords == ("Deprem", '"sel"')
