"""The per-outlet report, the summary and SearchResult (S8)."""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd

from tr_news_scraper._http import HostStats
from tr_news_scraper._table import (
    DATES_NOTE,
    REPORT_COLUMNS,
    OutletRun,
    Row,
    build_result,
    coverage_of,
    detail_of,
    status_of,
)
from tr_news_scraper.outlets import Month, MonthlySitemap, get
from tr_news_scraper.outlets._dates import ISTANBUL
from tr_news_scraper.outlets._model import Gap

FEB, MAR = Month(2023, 2), Month(2023, 3)
FEB_START, MAR_START, APR_START = date(2023, 2, 1), date(2023, 3, 1), date(2023, 4, 1)
SEARCHED_AT = datetime(2026, 11, 8, 10, 30, tzinfo=ISTANBUL)
STARTS_LATER = "the archive starts in 2023-12"
WINDOW = (
    "Milliyet's search has nothing older than 2024-05-25 for 'deprem', so the rest of the range "
    "can't be reached through it"
)


def boundary(month: Month, detail: str = STARTS_LATER) -> Gap:
    return Gap("before-archive", detail, month=month)


def window(reached: date | None, keyword: str = "deprem") -> Gap:
    return Gap("window", WINDOW, keyword=keyword, reached=reached)


def article(outlet: str, url: str) -> Row:
    return Row(
        outlet=outlet,
        url=f"https://www.example.com.tr/{url}",
        month=FEB,
        matched=("deprem",),
        reasons=("url: 'deprem' matches 'deprem' (prefix)",),
        source="https://www.example.com.tr/sitemaps/2023-02.xml",
    )


def test_status_is_ok_incomplete_or_failed() -> None:
    sozcu = get("sozcu")
    assert status_of(OutletRun(sozcu, gaps=[boundary(FEB)])) == "ok"
    failed_month = Gap("failed", "the file for 2023-02 couldn't be read: …", month=FEB)
    assert status_of(OutletRun(sozcu, gaps=[failed_month])) == "incomplete"
    assert status_of(OutletRun(sozcu, gaps=[Gap("robots", "…", month=FEB)])) == "incomplete"
    assert status_of(OutletRun(sozcu, failure="its sitemap index couldn't be read: …")) == "failed"


def test_a_sitemap_outlet_covers_all_part_or_none_of_the_range() -> None:
    sozcu = get("sozcu")
    assert coverage_of(OutletRun(sozcu), ("deprem",), FEB_START, APR_START) == "full"
    part = OutletRun(sozcu, gaps=[boundary(FEB)])
    assert coverage_of(part, ("deprem",), FEB_START, APR_START) == "partial"
    none = OutletRun(sozcu, gaps=[boundary(FEB), boundary(MAR)])
    assert coverage_of(none, ("deprem",), FEB_START, APR_START) == "none"
    failed = OutletRun(sozcu, failure="…")
    assert coverage_of(failed, ("deprem",), FEB_START, APR_START) == "unknown"


def test_a_failed_month_is_not_a_coverage_gap() -> None:
    run = OutletRun(get("sozcu"), gaps=[Gap("failed", "…", month=FEB)])
    assert coverage_of(run, ("deprem",), FEB_START, MAR_START) == "full"


def test_a_site_search_covers_none_of_the_range_when_every_keyword_stops_before_it() -> None:
    milliyet = get("milliyet")
    stopped = OutletRun(milliyet, gaps=[window(date(2024, 5, 25)), window(None, "sel*")])
    assert coverage_of(stopped, ("deprem", "sel*"), FEB_START, MAR_START) == "none"
    one_reaches = OutletRun(milliyet, gaps=[window(date(2024, 5, 25))])
    assert coverage_of(one_reaches, ("deprem", "sel"), FEB_START, MAR_START) == "partial"
    inside = OutletRun(milliyet, gaps=[window(date(2023, 2, 20))])
    assert coverage_of(inside, ("deprem",), FEB_START, MAR_START) == "partial"


def test_detail_keeps_three_distinct_sentences_then_counts_the_rest() -> None:
    sozcu = get("sozcu")
    assert detail_of(OutletRun(sozcu)) == ""
    repeated = OutletRun(sozcu, gaps=[boundary(FEB), boundary(MAR)])
    assert detail_of(repeated) == STARTS_LATER
    months = [Month(2001, n) for n in range(1, 6)]
    missing = [Gap("not-in-archive", f"the archive has no file for {m}", month=m) for m in months]
    assert detail_of(OutletRun(sozcu, gaps=missing)) == (
        "the archive has no file for 2001-01; the archive has no file for 2001-02; "
        "the archive has no file for 2001-03; and 2 more"
    )
    assert detail_of(OutletRun(sozcu, failure="its sitemap index couldn't be read")) == (
        "its sitemap index couldn't be read"
    )


def result_for(runs: list[OutletRun], stats: dict[str, HostStats] | None = None) -> pd.DataFrame:
    built = build_result(
        runs,
        keywords=("deprem",),
        start=FEB_START,
        end=MAR_START,
        outlets=tuple(run.outlet for run in runs),
        searched_at=SEARCHED_AT,
        version="1.0.0",
        stats=stats or {},
    )
    return built.report


def test_the_report_has_one_row_per_outlet_with_its_counts() -> None:
    cumhuriyet = OutletRun(
        get("cumhuriyet"),
        rows=[article("cumhuriyet", "a"), article("cumhuriyet", "b")],
        candidates=20,
        trimmed=1,
    )
    milliyet = OutletRun(get("milliyet"), candidates=3, unconfirmed=3, gaps=[window(None)])
    stats = {
        "www.cumhuriyet.com.tr": HostStats(requests=3, cache_hits=1, retries=1, errors=0),
        "www.milliyet.com.tr": HostStats(requests=11, blocked=1, robots_override=True),
    }
    report = result_for([cumhuriyet, milliyet], stats)
    assert tuple(report.columns) == REPORT_COLUMNS
    assert report.to_dict("records") == [
        {
            "outlet": "cumhuriyet",
            "name": "Cumhuriyet",
            "method": "monthly sitemap",
            "status": "ok",
            "coverage": "full",
            "articles": 2,
            "candidates": 20,
            "trimmed": 1,
            "unconfirmed": 0,
            "dates": "month",
            "detail": "",
            "requests": 3,
            "cache_hits": 1,
            "retries": 1,
            "errors": 0,
            "robots_override": False,
        },
        {
            "outlet": "milliyet",
            "name": "Milliyet",
            "method": "site search",
            "status": "ok",
            "coverage": "none",
            "articles": 0,
            "candidates": 3,
            "trimmed": 0,
            "unconfirmed": 3,
            "dates": "day",
            "detail": WINDOW,
            "requests": 11,
            "cache_hits": 0,
            "retries": 0,
            "errors": 1,
            "robots_override": True,
        },
    ]
    assert str(report["articles"].dtype) == "int64"
    assert str(report["robots_override"].dtype) == "bool"
    assert str(report["detail"].dtype) == "string"


def test_http_counts_add_up_over_all_of_an_outlets_hosts() -> None:
    two_hosts = MonthlySitemap(
        id="ornek",
        name="Örnek",
        index="https://www.example.com.tr/sitemaps/posts.xml",
        month_file=r"posts-(?P<year>\d{4})-(?P<month>\d{2})\.xml$",
        extra_hosts=frozenset({"m.example.com.tr"}),
    )
    stats = {
        "www.example.com.tr": HostStats(requests=2, cache_hits=1),
        "m.example.com.tr": HostStats(requests=5, retries=2, errors=1),
        "www.other.com.tr": HostStats(requests=100),
    }
    [record] = result_for([OutletRun(two_hosts)], stats).to_dict("records")
    counts = {key: record[key] for key in ("requests", "cache_hits", "retries", "errors")}
    assert counts == {"requests": 7, "cache_hits": 1, "retries": 2, "errors": 1}


def test_the_summary_explains_every_outlet_without_articles() -> None:
    runs = [
        OutletRun(get("cumhuriyet"), rows=[article("cumhuriyet", "a"), article("cumhuriyet", "b")]),
        OutletRun(get("sozcu"), gaps=[boundary(FEB)]),
        OutletRun(get("star"), failure="its sitemap index couldn't be read: HTTP 403"),
        OutletRun(get("milliyet"), gaps=[window(date(2024, 5, 25))]),
    ]
    result = build_result(
        runs,
        keywords=("deprem", "sel"),
        start=FEB_START,
        end=MAR_START,
        outlets=tuple(run.outlet for run in runs),
        searched_at=SEARCHED_AT,
        version="1.0.0",
        stats={},
    )
    assert str(result) == "\n".join(
        [
            "deprem, sel, 2023-02-01 to 2023-02-28: 2 articles from 1 of 4 outlets",
            "  Cumhuriyet  2",
            f"  Sözcü       0  {STARTS_LATER}",
            "  Star        0  failed: its sitemap index couldn't be read: HTTP 403",
            f"  Milliyet    0  {WINDOW}",
            DATES_NOTE,
        ]
    )
    assert repr(result) == (
        "SearchResult(deprem, sel, 2023-02-01 to 2023-02-28: 2 articles from 1 of 4 outlets)"
    )
    assert (result.keywords, result.start, result.end) == (("deprem", "sel"), FEB_START, MAR_START)
    assert (result.searched_at, result.version) == (SEARCHED_AT, "1.0.0")
    assert len(result.articles) == 2
    assert list(result.gaps["outlet"]) == ["sozcu", "milliyet"]


def test_a_one_day_search_names_its_day_and_an_incomplete_outlet_says_so() -> None:
    run = OutletRun(
        get("trt-haber"),
        rows=[article("trt-haber", "a")],
        gaps=[Gap("failed", "the file for 2023-02 couldn't be read: HTTP 503", month=FEB)],
    )
    result = build_result(
        [run],
        keywords=("deprem",),
        start=date(2023, 2, 6),
        end=date(2023, 2, 7),
        outlets=(run.outlet,),
        searched_at=SEARCHED_AT,
        version="1.0.0",
        stats={},
    )
    lines = str(result).splitlines()
    assert lines[0] == "deprem, 2023-02-06: 1 article from 1 of 1 outlet"
    assert lines[1] == (
        "  TRT Haber  1  incomplete: the file for 2023-02 couldn't be read: HTTP 503"
    )


def test_a_summary_without_month_dated_rows_skips_the_dates_note() -> None:
    result = build_result(
        [OutletRun(get("sozcu"), gaps=[boundary(FEB)])],
        keywords=("deprem",),
        start=FEB_START,
        end=MAR_START,
        outlets=(get("sozcu"),),
        searched_at=SEARCHED_AT,
        version="1.0.0",
        stats={},
    )
    assert str(result).splitlines()[-1] == f"  Sözcü  0  {STARTS_LATER}"
