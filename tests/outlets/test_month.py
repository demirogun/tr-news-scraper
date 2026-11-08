"""Months: the unit monthly sitemaps are filed by."""

from __future__ import annotations

from datetime import date

import pytest

from tr_news_scraper.outlets import Month


def test_a_month_prints_as_year_and_month() -> None:
    assert str(Month(2023, 2)) == "2023-02"
    assert str(Month(1962, 8)) == "1962-08"


def test_months_are_ordered_and_hashable() -> None:
    assert Month(2022, 12) < Month(2023, 1) < Month(2023, 2)
    assert {Month(2023, 2), Month(2023, 2)} == {Month(2023, 2)}


def test_a_month_knows_its_first_day_and_neighbours() -> None:
    assert Month.of(date(2023, 2, 6)) == Month(2023, 2)
    assert Month(2023, 2).start == date(2023, 2, 1)
    assert Month(2022, 12).next() == Month(2023, 1)
    assert Month(2023, 1).previous() == Month(2022, 12)
    assert Month(2023, 6).next().previous() == Month(2023, 6)


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        (date(2023, 2, 1), date(2023, 3, 1), [Month(2023, 2)]),
        (date(2023, 2, 6), date(2023, 2, 7), [Month(2023, 2)]),
        (
            date(2023, 1, 15),
            date(2023, 3, 10),
            [Month(2023, 1), Month(2023, 2), Month(2023, 3)],
        ),
        (date(2022, 12, 31), date(2023, 1, 2), [Month(2022, 12), Month(2023, 1)]),
    ],
)
def test_span_lists_every_month_the_range_touches(
    start: date, end: date, expected: list[Month]
) -> None:
    assert Month.span(start, end) == expected


def test_a_range_that_ends_on_the_first_of_a_month_leaves_that_month_out() -> None:
    assert Month.span(date(2023, 1, 1), date(2023, 2, 1)) == [Month(2023, 1)]


@pytest.mark.parametrize("end", [date(2023, 2, 1), date(2023, 1, 31)])
def test_span_needs_a_range_that_isnt_empty(end: date) -> None:
    with pytest.raises(ValueError, match="must be before"):
        Month.span(date(2023, 2, 1), end)


@pytest.mark.parametrize(("year", "month"), [(2023, 0), (2023, 13), (0, 1), (10_000, 1)])
def test_impossible_months_are_refused(year: int, month: int) -> None:
    with pytest.raises(ValueError, match="not a calendar month"):
        Month(year, month)
