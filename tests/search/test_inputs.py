"""search()'s inputs are checked before any request (S1)."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from tr_news_scraper._search import parse_keywords, parse_range, resolve_outlets
from tr_news_scraper.outlets import MonthlySitemap, builtin, get
from tr_news_scraper.outlets._dates import ISTANBUL

ORNEK = MonthlySitemap(
    id="ornek-gazete",
    name="Örnek Gazete",
    index="https://www.example.com.tr/sitemaps/posts.xml",
    month_file=r"/sitemaps/posts-(?P<year>\d{4})-(?P<month>\d{2})\.xml$",
)


def test_a_string_is_one_keyword() -> None:
    assert parse_keywords("toprak kayması") == ("toprak kayması",)


def test_blank_and_repeated_keywords_are_dropped_keeping_the_first_spelling() -> None:
    assert parse_keywords(["deprem", " ", "DEPREM", " sel ", "deprem"]) == ("deprem", "sel")


def test_operators_make_different_keywords() -> None:
    assert parse_keywords(["sel", '"sel"', "sel*"]) == ("sel", '"sel"', "sel*")


@pytest.mark.parametrize("keywords", [[], ["", "  "], "", "   "])
def test_at_least_one_keyword_is_needed(keywords: list[str] | str) -> None:
    with pytest.raises(ValueError, match="give at least one keyword"):
        parse_keywords(keywords)


def test_keywords_must_be_strings() -> None:
    with pytest.raises(TypeError, match="keywords must be strings, not int"):
        parse_keywords(["deprem", 7])  # type: ignore[list-item]


def test_days_can_be_dates_or_iso_strings() -> None:
    assert parse_range(" 2023-02-01", date(2023, 3, 1)) == (date(2023, 2, 1), date(2023, 3, 1))


def test_a_datetime_is_refused_because_a_range_is_whole_days() -> None:
    with pytest.raises(TypeError, match="start must be a date, not a datetime"):
        parse_range(datetime(2023, 2, 1, tzinfo=ISTANBUL), "2023-03-01")


@pytest.mark.parametrize("text", ["2023-2-1", "01.02.2023", "2023-02-30", "yesterday"])
def test_a_day_must_be_written_as_yyyy_mm_dd(text: str) -> None:
    with pytest.raises(ValueError, match=r"end must be a date or 'YYYY-MM-DD', such as"):
        parse_range("2023-02-01", text)


def test_a_day_of_another_type_is_refused() -> None:
    with pytest.raises(TypeError, match="start must be a date or 'YYYY-MM-DD', not int"):
        parse_range(20230201, "2023-03-01")  # type: ignore[arg-type]


def test_the_start_must_come_before_the_end() -> None:
    with pytest.raises(
        ValueError, match=r"the start \(2023-03-01\) must be before the end \(2023-03-01\)"
    ):
        parse_range("2023-03-01", "2023-03-01")


def test_outlets_default_to_every_built_in_outlet() -> None:
    assert resolve_outlets(None) == builtin()


def test_outlets_keep_the_order_given_and_accept_definitions() -> None:
    assert resolve_outlets(["star", ORNEK, "cumhuriyet"]) == (get("star"), ORNEK, get("cumhuriyet"))


def test_a_single_id_or_definition_is_one_outlet() -> None:
    assert resolve_outlets("star") == (get("star"),)
    assert resolve_outlets(ORNEK) == (ORNEK,)


def test_an_unknown_outlet_names_the_valid_ids() -> None:
    with pytest.raises(ValueError, match="no built-in outlet 'hurriyet'; choose from cumhuriyet"):
        resolve_outlets(["hurriyet"])


def test_two_outlets_cannot_share_an_id() -> None:
    with pytest.raises(ValueError, match="two outlets share the id 'star'"):
        resolve_outlets(["star", get("star")])


def test_at_least_one_outlet_is_needed() -> None:
    with pytest.raises(ValueError, match="choose at least one outlet"):
        resolve_outlets([])


def test_outlets_must_be_ids_or_definitions() -> None:
    with pytest.raises(TypeError, match="outlets must be outlet ids or definitions, not int"):
        resolve_outlets([3])  # type: ignore[list-item]
