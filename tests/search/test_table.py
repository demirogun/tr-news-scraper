"""The article and gap tables (S5 to S7): one row per URL, in a fixed order, with fixed dtypes."""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd

import tr_news_scraper._table as table
from tr_news_scraper._table import (
    ARTICLE_COLUMNS,
    GAP_COLUMNS,
    OutletRun,
    Row,
    articles_frame,
    gaps_frame,
    merge,
)
from tr_news_scraper.outlets import Month, get
from tr_news_scraper.outlets._dates import ISTANBUL
from tr_news_scraper.outlets._model import Gap

JAN, FEB = Month(2023, 1), Month(2023, 2)
KEYWORDS = ("deprem", "sel")
ORDER = {"cumhuriyet": 0, "milliyet": 1}


def row(
    url: str,
    month: Month = FEB,
    *,
    outlet: str = "cumhuriyet",
    matched: tuple[str, ...] = ("deprem",),
    reasons: tuple[str, ...] = ("url: 'deprem' matches 'deprem' (prefix)",),
    title: str | None = None,
    day: date | None = None,
    lastmod: datetime | None = None,
) -> Row:
    return Row(
        outlet=outlet,
        url=f"https://www.example.com.tr/{url}",
        month=month,
        matched=matched,
        reasons=reasons,
        source=f"https://www.example.com.tr/sitemaps/{month}.xml",
        title=title,
        day=day,
        lastmod=lastmod,
    )


def test_a_url_found_twice_becomes_one_row_with_both_matches() -> None:
    edited = datetime(2023, 2, 3, tzinfo=ISTANBUL)
    rows = [
        row("a", FEB, matched=("sel",), reasons=("url: 'sel' matches 'sel' (stem)",), title="A"),
        row("a", JAN, lastmod=edited),
        row("a", FEB, reasons=("url: 'deprem' matches 'deprem' (prefix)",), title="B"),
    ]
    [merged] = merge(rows, KEYWORDS, ORDER)
    assert merged.month == JAN
    assert merged.matched == ("deprem", "sel")
    assert merged.reasons == (
        "url: 'deprem' matches 'deprem' (prefix)",
        "url: 'sel' matches 'sel' (stem)",
    )
    assert (merged.title, merged.lastmod, merged.source) == ("A", edited, rows[1].source)


def test_a_merged_row_keeps_the_first_day_found() -> None:
    rows = [
        row("a", outlet="milliyet", day=date(2023, 2, 6)),
        row("a", outlet="milliyet", day=date(2023, 2, 7)),
    ]
    assert [r.day for r in merge(rows, KEYWORDS, ORDER)] == [date(2023, 2, 6)]


def test_rows_are_ordered_by_month_outlet_day_and_url() -> None:
    rows = [
        row("z", FEB),
        row("m/b", FEB, outlet="milliyet", day=date(2023, 2, 7)),
        row("m/c", FEB, outlet="milliyet"),
        row("m/a", FEB, outlet="milliyet", day=date(2023, 2, 9)),
        row("y", JAN),
        row("a", FEB),
    ]
    ordered = [(r.month, r.outlet, r.url[-1]) for r in merge(rows, KEYWORDS, ORDER)]
    assert ordered == [
        (JAN, "cumhuriyet", "y"),
        (FEB, "cumhuriyet", "a"),
        (FEB, "cumhuriyet", "z"),
        (FEB, "milliyet", "b"),
        (FEB, "milliyet", "a"),
        (FEB, "milliyet", "c"),
    ]


def test_the_article_table_has_the_promised_columns_and_types() -> None:
    edited = datetime(2023, 2, 28, 22, 46, tzinfo=ISTANBUL)
    frame = articles_frame(
        [
            row(
                "a",
                matched=("deprem", "sel"),
                reasons=(
                    "title: 'deprem' matches 'deprem' (prefix)",
                    "url: 'sel' matches 'sel' (stem)",
                ),
                title="Deprem ve sel",
                lastmod=edited,
            ),
            row("b", outlet="milliyet", day=date(2023, 2, 6)),
        ]
    )
    assert tuple(frame.columns) == ARTICLE_COLUMNS
    assert {name: str(frame[name].dtype) for name in frame.columns} == {
        "outlet": "string",
        "month": "string",
        "day": "datetime64[ns]",
        "title": "string",
        "url": "string",
        "matched": "string",
        "reasons": "string",
        "lastmod": "datetime64[ns, Europe/Istanbul]",
        "source": "string",
    }
    first, second = frame.iloc[0], frame.iloc[1]
    assert (first["month"], first["matched"]) == ("2023-02", "deprem, sel")
    assert first["reasons"] == (
        "title: 'deprem' matches 'deprem' (prefix); url: 'sel' matches 'sel' (stem)"
    )
    assert first["lastmod"] == pd.Timestamp(edited)
    assert pd.isna(first["day"])
    assert second["day"] == pd.Timestamp(2023, 2, 6)
    assert pd.isna(second["title"])
    assert pd.isna(second["lastmod"])
    assert list(frame.index) == [0, 1]


def test_an_empty_article_table_keeps_its_columns_and_types() -> None:
    frame = articles_frame([])
    assert tuple(frame.columns) == ARTICLE_COLUMNS
    assert len(frame) == 0
    assert str(frame["day"].dtype) == "datetime64[ns]"
    assert str(frame["lastmod"].dtype) == "datetime64[ns, Europe/Istanbul]"
    assert str(frame["url"].dtype) == "string"


def test_the_gap_table_lists_every_gap_by_outlet() -> None:
    runs = [
        OutletRun(
            get("sozcu"),
            gaps=[Gap("before-archive", "the archive starts in 2023-12", month=FEB)],
        ),
        OutletRun(
            get("milliyet"),
            gaps=[
                Gap(
                    "failed",
                    "the search for 'sel' couldn't be read: it isn't well-formed XML",
                    keyword="sel",
                    url="https://www.milliyet.com.tr/api/search/searchcontentloadmore?query=sel&page=1",
                )
            ],
        ),
    ]
    frame = gaps_frame(runs)
    assert tuple(frame.columns) == GAP_COLUMNS
    assert {str(dtype) for dtype in frame.dtypes} == {"string"}
    assert list(frame["outlet"]) == ["sozcu", "milliyet"]
    assert list(frame["reason"]) == ["before-archive", "failed"]
    assert frame.loc[0, "detail"] == "the archive starts in 2023-12"
    assert frame.loc[0, "month"] == "2023-02"
    assert frame.loc[1, "keyword"] == "sel"
    assert str(frame.loc[1, "url"]).endswith("query=sel&page=1")
    missing = {name: frame[name].isna().tolist() for name in ("month", "keyword", "url")}
    assert missing == {"month": [False, True], "keyword": [True, False], "url": [True, False]}


def test_the_table_module_imports_pandas_only_inside_its_functions() -> None:
    assert "pd" not in vars(table)
    assert "pandas" not in vars(table)
