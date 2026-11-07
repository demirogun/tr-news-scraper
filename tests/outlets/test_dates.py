"""Dates in archives: sitemap ``<lastmod>`` values and search-result days."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from tr_news_scraper.outlets._dates import ISTANBUL, parse_day, parse_lastmod


@pytest.mark.parametrize(
    ("text", "expected", "offset_hours"),
    [
        (  # Cumhuriyet, TRT Haber, Star
            "2023-02-28T23:41:19+03:00",
            datetime(2023, 2, 28, 23, 41, 19, tzinfo=timezone(timedelta(hours=3))),
            3,
        ),
        (  # Euronews Türkçe
            "2023-02-01T05:19:41+01:00",
            datetime(2023, 2, 1, 5, 19, 41, tzinfo=timezone(timedelta(hours=1))),
            1,
        ),
        (  # DW-style UTC with milliseconds
            "2026-11-07T10:18:04.268Z",
            datetime(2026, 11, 7, 10, 18, 4, 268_000, tzinfo=UTC),
            0,
        ),
    ],
)
def test_a_lastmod_with_an_offset_keeps_it(
    text: str, expected: datetime, offset_hours: int
) -> None:
    parsed = parse_lastmod(text)
    assert parsed == expected
    assert parsed is not None
    assert parsed.utcoffset() == timedelta(hours=offset_hours)


def test_surrounding_whitespace_is_ignored() -> None:
    assert parse_lastmod("\n  2023-02-01T00:01:00+03:00 ") == datetime(
        2023, 2, 1, 0, 1, tzinfo=timezone(timedelta(hours=3))
    )


def test_a_date_without_a_time_is_midnight_in_istanbul() -> None:
    parsed = parse_lastmod("2023-02-01")
    assert parsed == datetime(2023, 2, 1, tzinfo=ISTANBUL)
    assert parsed is not None
    assert parsed.utcoffset() == timedelta(hours=3)


def test_a_time_without_an_offset_is_istanbul_time() -> None:
    parsed = parse_lastmod("2023-02-06T04:17:00")
    assert parsed is not None
    assert parsed.utcoffset() == timedelta(hours=3)
    assert parsed.astimezone(UTC) == datetime(2023, 2, 6, 1, 17, tzinfo=UTC)


def test_istanbul_winters_before_2016_were_utc_plus_two() -> None:
    # A fixed +03:00 would get this wrong; the zone database gets it right.
    parsed = parse_lastmod("2011-01-15T12:00:00")
    assert parsed is not None
    assert parsed.utcoffset() == timedelta(hours=2)


@pytest.mark.parametrize(
    "text", [None, "", "   ", "dün", "2023-02", "2023-13-01", "2023-02-30T10:00:00+03:00"]
)
def test_missing_or_unreadable_lastmod_is_none(text: str | None) -> None:
    assert parse_lastmod(text) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [("7.11.2026", date(2026, 11, 7)), (" 26.05.2024\n", date(2024, 5, 26))],
)
def test_days_are_read_in_the_outlets_format(text: str, expected: date) -> None:
    assert parse_day(text, "%d.%m.%Y") == expected


@pytest.mark.parametrize("text", [None, "", "dün", "2026-11-07", "32.01.2026", "7.11.2026 14:05"])
def test_days_that_dont_fit_the_format_are_none(text: str | None) -> None:
    assert parse_day(text, "%d.%m.%Y") is None
