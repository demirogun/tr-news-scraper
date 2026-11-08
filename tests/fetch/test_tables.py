"""The fetched tables (F5, F6, D1, D2, D10): added columns, filled days and titles, rows outside
the range set apart, the report and the summary."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pandas as pd
import pytest

from tr_news_scraper._extract import Extracted
from tr_news_scraper._fetch import Fetched, FetchRun
from tr_news_scraper._fetched import (
    ADDED_COLUMNS,
    FETCH_REPORT_COLUMNS,
    build_fetch_result,
    clean_headline,
)
from tr_news_scraper._http import HostStats
from tr_news_scraper._table import ARTICLE_COLUMNS, Row, articles_frame
from tr_news_scraper.outlets import Month, get
from tr_news_scraper.outlets._dates import ISTANBUL

FEB = Month(2023, 2)
START, END = date(2023, 2, 1), date(2023, 3, 1)
NOW = datetime(2026, 11, 8, 12, 0, tzinfo=ISTANBUL)
DOWNLOADED = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)
STORY = " ".join(f"ajans{n}" for n in range(60)) + " deprem"
OUTLETS = (get("star"), get("trt-haber"), get("euronews-tr"))


def row(outlet: str, url: str, title: str | None = None) -> Row:
    return Row(
        outlet=outlet,
        url=f"https://www.example.com.tr/{url}",
        month=FEB,
        matched=("deprem",),
        reasons=("url: 'deprem' matches 'deprem' (prefix)",),
        source="https://www.example.com.tr/sitemap.xml",
        title=title,
    )


def page(
    text: str | None = STORY,
    published: datetime | None = datetime(2023, 2, 12, 6, 2, tzinfo=ISTANBUL),
    *,
    title: str | None = "Sayfadaki başlık",
    error: str | None = None,
    cached: bool = False,
) -> Fetched:
    extracted = Extracted(title=title, author="IHA", published=published, text=text, error=error)
    return Fetched(extracted, None if error else DOWNLOADED, cached=cached)


def search_table() -> pd.DataFrame:
    return articles_frame(
        [
            row("star", "a", title="Arşivdeki başlık"),
            row("trt-haber", "b"),
            row("trt-haber", "c"),
            row("euronews-tr", "d"),
            row("euronews-tr", "e"),
        ]
    )


def runs() -> list[FetchRun]:
    star = FetchRun(OUTLETS[0], {0: page()}, downloaded=1)
    trt = FetchRun(
        OUTLETS[1],
        {
            1: page(title="TRT başlığı - TRT Haber", cached=True),
            2: page(
                published=datetime(2023, 3, 2, 23, 48, tzinfo=ISTANBUL), text="Başka bir haber"
            ),
        },
        downloaded=1,
        cached=1,
    )
    euronews = FetchRun(
        OUTLETS[2],
        {
            3: page(published=None, text="Tarihsiz bir haber metni"),
            4: page(
                error="the request failed (HTTP 404, 1 attempt)",
                text=None,
                title=None,
                published=None,
            ),
        },
        downloaded=1,
        failed=1,
    )
    return [star, trt, euronews]


def build(
    stats: dict[str, HostStats] | None = None, *, keywords: tuple[str, ...] = ("deprem",)
) -> object:
    return build_fetch_result(
        search_table(),
        runs(),
        keywords=keywords,
        start=START,
        end=END,
        outlets=OUTLETS,
        fetched_at=NOW,
        version="1.0.0",
        stats=stats or {},
    )


def test_fetch_adds_its_columns_after_searchs_with_fixed_types() -> None:
    result = build()
    frame = result.articles  # type: ignore[attr-defined]
    assert tuple(frame.columns) == (*ARTICLE_COLUMNS, *ADDED_COLUMNS)
    assert {name: str(frame[name].dtype) for name in ADDED_COLUMNS} == {
        "published": "datetime64[ns, Europe/Istanbul]",
        "author": "string",
        "text": "string",
        "text_matched": "string",
        "copy_group": "Int64",
        "fetched_at": "datetime64[ns, Europe/Istanbul]",
        "error": "string",
    }


def test_rows_dated_outside_the_range_move_to_outside() -> None:
    result = build()
    assert list(result.articles["url"].str[-1]) == ["a", "b", "d", "e"]  # type: ignore[attr-defined]
    outside = result.outside  # type: ignore[attr-defined]
    assert list(outside["url"].str[-1]) == ["c"]
    assert outside.loc[0, "published"] == pd.Timestamp(
        datetime(2023, 3, 2, 23, 48, tzinfo=ISTANBUL)
    )


def test_day_and_title_are_filled_only_where_search_left_them_empty() -> None:
    articles = build().articles  # type: ignore[attr-defined]
    assert articles.loc[0, "title"] == "Arşivdeki başlık"
    assert articles.loc[1, "title"] == "TRT başlığı"
    assert articles.loc[2, "title"] == "Sayfadaki başlık"
    assert pd.isna(articles.loc[3, "title"])
    assert articles.loc[0, "day"] == pd.Timestamp(2023, 2, 12)
    assert articles["day"].isna().tolist() == [False, False, True, True]


def test_text_matched_copy_group_fetched_at_and_error() -> None:
    articles = build().articles  # type: ignore[attr-defined]
    assert list(articles["text_matched"]) == ["deprem", "deprem", "", ""]
    assert articles["copy_group"].tolist() == [1, 1, pd.NA, pd.NA]
    assert articles.loc[0, "fetched_at"] == pd.Timestamp(DOWNLOADED)
    assert str(articles.loc[0, "fetched_at"].tz) == "Europe/Istanbul"
    assert articles["error"].isna().tolist() == [True, True, True, False]
    assert articles.loc[3, "error"] == "the request failed (HTTP 404, 1 attempt)"


def test_the_report_counts_each_outlets_rows() -> None:
    stats = {"www.trthaber.com": HostStats(requests=3, cache_hits=1)}
    report = build(stats).report  # type: ignore[attr-defined]
    assert tuple(report.columns) == FETCH_REPORT_COLUMNS
    records = {record["outlet"]: record for record in report.to_dict("records")}
    trt = records["trt-haber"]
    counts = ("articles", "downloaded", "cached", "failed", "outside", "undated", "copies")
    assert tuple(trt[name] for name in counts) == (2, 1, 1, 0, 1, 0, 1)
    assert (trt["requests"], trt["cache_hits"]) == (3, 1)
    euronews = records["euronews-tr"]
    assert tuple(euronews[name] for name in counts) == (2, 1, 0, 1, 0, 1, 0)
    assert euronews["detail"] == "1 × the request failed (HTTP 404, 1 attempt)"
    assert records["star"]["detail"] == ""


def test_the_summary_counts_reads_failures_and_copies() -> None:
    result = build()
    assert str(result).splitlines() == [
        "deprem, 2023-02-01 to 2023-02-28: 3 articles read, 1 outside the range, 1 failed",
        "  Star             1",
        "  TRT Haber        1",
        "  Euronews Türkçe  1  1 failed: 1 × the request failed (HTTP 404, 1 attempt)",
        "2 articles are copies of a story another article also carries (copy_group).",
    ]
    assert repr(result) == (
        "FetchResult(deprem, 2023-02-01 to 2023-02-28: 3 articles read, 1 outside the range, "
        "1 failed)"
    )


def test_a_plain_table_without_a_range_keeps_every_row_and_gains_day_and_title() -> None:
    plain = pd.DataFrame(
        {
            "outlet": pd.Series(["star"], dtype="string"),
            "url": pd.Series(["https://www.star.com.tr/a"], dtype="string"),
        }
    )
    result = build_fetch_result(
        plain,
        [FetchRun(OUTLETS[0], {0: page(published=datetime(2020, 1, 1, tzinfo=ISTANBUL))})],
        keywords=(),
        start=None,
        end=None,
        outlets=OUTLETS[:1],
        fetched_at=NOW,
        version="1.0.0",
        stats={},
    )
    assert tuple(result.articles.columns) == ("outlet", "url", "day", "title", *ADDED_COLUMNS)
    assert len(result.articles) == 1
    assert len(result.outside) == 0
    assert result.articles.loc[0, "text_matched"] == ""
    assert str(result).splitlines()[0] == "1 article read, 0 failed"


@pytest.mark.parametrize(
    ("title", "outlet", "cleaned"),
    [
        (
            "Hatay'da 4,1 büyüklüğünde deprem - Sözcü Gazetesi",
            "Sözcü",
            "Hatay'da 4,1 büyüklüğünde deprem",
        ),
        ("Göl çamura bulandı | STAR", "Star", "Göl çamura bulandı"),
        ("Deprem - Kahramanmaraş - TRT Haber", "TRT Haber", "Deprem - Kahramanmaraş"),
        ("Yardım - Almanya'dan haber", "Akşam", "Yardım - Almanya'dan haber"),
        ("Akşam", "Akşam", "Akşam"),
        (None, "Star", None),
    ],
)
def test_a_page_headline_loses_a_trailing_part_that_names_the_outlet(
    title: str | None, outlet: str, cleaned: str | None
) -> None:
    assert clean_headline(title, outlet) == cleaned


def test_the_detail_names_the_three_commonest_reasons_then_counts_the_rest() -> None:
    from collections import Counter

    from tr_news_scraper._fetched import _detail

    reasons = Counter({"a": 5, "b": 3, "c": 2, "d": 1, "e": 1})
    assert _detail(reasons) == "5 × a; 3 × b; 2 × c; and 2 more"
    assert _detail(Counter()) == ""


def test_a_row_dated_before_the_start_also_moves_to_outside() -> None:
    table = articles_frame([row("star", "a")])
    early = FetchRun(OUTLETS[0], {0: page(published=datetime(2023, 1, 31, 23, 0, tzinfo=ISTANBUL))})
    result = build_fetch_result(
        table,
        [early],
        keywords=("deprem",),
        start=START,
        end=END,
        outlets=OUTLETS[:1],
        fetched_at=NOW,
        version="1.0.0",
        stats={},
    )
    assert (len(result.articles), len(result.outside)) == (0, 1)
