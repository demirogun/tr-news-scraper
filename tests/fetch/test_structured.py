"""Structured data on article pages (F3a, F3c): JSON-LD's article object and its times."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from tr_news_scraper._structured import (
    MAX_JSON_LD_CHARACTERS,
    find_article,
    json_ld_objects,
    read_time,
)
from tr_news_scraper.outlets._dates import ISTANBUL


def article_in(*blocks: str) -> dict[str, object] | None:
    return find_article(json_ld_objects(blocks))


def test_a_single_object_is_the_article() -> None:
    block = '{"@context": "https://schema.org", "@type": "NewsArticle", "headline": "Başlık"}'
    assert article_in(block) == {
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": "Başlık",
    }


def test_an_article_inside_a_graph_is_found() -> None:
    block = json.dumps(
        {
            "@context": "https://schema.org",
            "@graph": [
                {"@type": "WebSite", "name": "Örnek"},
                {"@type": "BreadcrumbList", "itemListElement": []},
                {"@type": "NewsArticle", "headline": "Grafikteki haber"},
            ],
        }
    )
    article = article_in(block)
    assert article is not None
    assert article["headline"] == "Grafikteki haber"


def test_a_list_of_objects_is_read_in_order() -> None:
    block = json.dumps(
        [{"@type": "Organization", "name": "Örnek"}, {"@type": "ReportageNews", "headline": "A"}]
    )
    article = article_in(block)
    assert article is not None
    assert article["headline"] == "A"


@pytest.mark.parametrize(
    "kind",
    [
        "NewsArticle",
        "Article",
        "ReportageNews",
        "AnalysisNewsArticle",
        "OpinionNewsArticle",
        "BackgroundNewsArticle",
        "BlogPosting",
        "LiveBlogPosting",
        ["WebPage", "NewsArticle"],
        "https://schema.org/NewsArticle",
        "schema:NewsArticle",
    ],
)
def test_every_kind_of_news_article_counts(kind: object) -> None:
    assert article_in(json.dumps({"@type": kind, "headline": "A"})) is not None


@pytest.mark.parametrize("kind", ["WebPage", ["WebPage", "ItemPage"], "VideoObject", None, 7, []])
def test_other_types_are_not_articles(kind: object) -> None:
    assert article_in(json.dumps({"@type": kind, "headline": "A"})) is None


def test_the_first_article_across_blocks_wins() -> None:
    first = '{"@type": "WebSite", "name": "Örnek"}'
    second = '{"@type": "NewsArticle", "headline": "Birinci"}'
    third = '{"@type": "NewsArticle", "headline": "İkinci"}'
    article = article_in(first, second, third)
    assert article is not None
    assert article["headline"] == "Birinci"


def test_a_block_that_isnt_json_is_skipped() -> None:
    broken = '{"@type": "NewsArticle", "headline": "Bozuk",}'
    fine = '{"@type": "NewsArticle", "headline": "Sağlam"}'
    article = article_in(broken, fine)
    assert article is not None
    assert article["headline"] == "Sağlam"


def test_a_raw_line_break_inside_a_string_is_accepted() -> None:
    block = '{"@type": "NewsArticle", "headline": "Birinci satır\nikinci satır"}'
    article = article_in(block)
    assert article is not None
    assert article["headline"] == "Birinci satır\nikinci satır"


def test_an_oversized_block_is_skipped() -> None:
    padding = "a" * MAX_JSON_LD_CHARACTERS
    block = json.dumps({"@type": "NewsArticle", "headline": "Büyük", "x": padding})
    assert article_in(block) is None


def test_deeply_nested_json_is_skipped_not_a_crash() -> None:
    hostile = "[" * 200_000 + "]" * 200_000
    fine = '{"@type": "NewsArticle", "headline": "Sağlam"}'
    article = article_in(hostile, fine)
    assert article is not None
    assert article["headline"] == "Sağlam"


@pytest.mark.parametrize("block", ['"bir metin"', "42", "null", '{"@graph": "yok"}', ""])
def test_json_that_holds_no_object_gives_no_article(block: str) -> None:
    assert article_in(block) is None


def test_a_page_without_json_ld_has_no_article() -> None:
    assert article_in() is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2023-02-06T23:30:00+03:00", datetime(2023, 2, 6, 23, 30, tzinfo=ISTANBUL)),
        # Another offset near midnight: really 01:30 the next day in Türkiye.
        ("2023-02-06T23:30:00+01:00", datetime(2023, 2, 7, 1, 30, tzinfo=ISTANBUL)),
        ("2023-02-06T20:30:00Z", datetime(2023, 2, 6, 23, 30, tzinfo=ISTANBUL)),
        ("2023-02-06T22:30:00.250+0100", datetime(2023, 2, 7, 0, 30, 0, 250_000, ISTANBUL)),
        # No offset: read as Türkiye's time.
        ("2023-02-06T23:30:00", datetime(2023, 2, 6, 23, 30, tzinfo=ISTANBUL)),
        ("2023-02-06 23:30", datetime(2023, 2, 6, 23, 30, tzinfo=ISTANBUL)),
        # A date alone gives midnight: only the day is known.
        ("2023-02-06", datetime(2023, 2, 6, tzinfo=ISTANBUL)),
        # Türkiye was on UTC+2 in the winter of 2014.
        ("2014-01-15T10:00:00", datetime(2014, 1, 15, 10, 0, tzinfo=ISTANBUL)),
        (" 2023-02-06T23:30:00+03:00 ", datetime(2023, 2, 6, 23, 30, tzinfo=ISTANBUL)),
        (
            ["2023-02-06T23:30:00+03:00", "2023-02-07"],
            datetime(2023, 2, 6, 23, 30, tzinfo=ISTANBUL),
        ),
    ],
)
def test_publication_times_keep_their_offset_and_come_out_in_istanbul(
    text: object, expected: datetime
) -> None:
    found = read_time(text)
    assert found == expected
    assert found is not None
    assert found.tzinfo is ISTANBUL
    assert found.utcoffset() == expected.utcoffset()


def test_a_2014_winter_time_is_two_hours_ahead_of_utc() -> None:
    found = read_time("2014-01-15T10:00:00")
    assert found is not None
    assert found.utcoffset() == timedelta(hours=2)


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "   ",
        "06.02.2023 23:30",
        "6 Şubat 2023",
        "dün",
        42,
        {"@value": "2023-02-06"},
        [],
        [3, None],
        "0001-01-01T00:00:00+14:00",
        "9999-12-31T23:59:59-12:00",
    ],
)
def test_anything_else_gives_no_time(value: object) -> None:
    assert read_time(value) is None
