"""Dates before fetch() (S4): what an archive says about when an article appeared."""

from __future__ import annotations

from datetime import UTC, date, datetime

from tr_news_scraper._search import collect, edited_before
from tr_news_scraper._table import OutletRun
from tr_news_scraper.matching import KeywordQuery
from tr_news_scraper.outlets import Candidate, Month, get
from tr_news_scraper.outlets._dates import ISTANBUL

FEB = Month(2023, 2)
START = date(2023, 2, 10)
END = date(2023, 3, 1)
QUERY = KeywordQuery(["deprem"])


def entry(
    lastmod: datetime | None, *, url: str = "deprem-2045001", month: Month = FEB
) -> Candidate:
    return Candidate(
        outlet="cumhuriyet",
        url=f"https://www.cumhuriyet.com.tr/turkiye/{url}",
        month=month,
        lastmod=lastmod,
        source="https://www.cumhuriyet.com.tr/sitemaps/posts-2023-2.xml",
    )


def result(day: date, url: str = "deprem-haberi-1") -> Candidate:
    return Candidate(
        outlet="milliyet",
        url=f"https://www.milliyet.com.tr/gundem/{url}",
        month=Month.of(day),
        title="Deprem haberi",
        day=day,
        source="https://www.milliyet.com.tr/api/search/searchcontentloadmore?query=deprem&page=3",
    )


def test_an_entry_without_a_last_edit_time_stays() -> None:
    assert not edited_before(entry(None), START)


def test_an_entry_last_edited_more_than_a_day_before_the_start_is_out() -> None:
    assert edited_before(entry(datetime(2023, 2, 8, 23, 59, tzinfo=ISTANBUL)), START)


def test_an_entry_edited_the_day_before_the_start_stays() -> None:
    # The extra day absorbs sites that write UTC times without an offset.
    assert not edited_before(entry(datetime(2023, 2, 9, 0, 0, tzinfo=ISTANBUL)), START)


def test_the_margin_is_measured_in_turkiyes_time_zone() -> None:
    # 22:30 UTC on the 8th is 01:30 on the 9th in Istanbul: inside the margin.
    assert not edited_before(entry(datetime(2023, 2, 8, 22, 30, tzinfo=UTC)), START)
    # 20:30 UTC on the 8th is 23:30 on the 8th in Istanbul: out.
    assert edited_before(entry(datetime(2023, 2, 8, 20, 30, tzinfo=UTC)), START)


def test_a_last_edit_before_the_entrys_own_month_cannot_rule_it_out() -> None:
    # Akşam's February 2023 file lists articles last edited in 2021 and 2022.
    assert not edited_before(entry(datetime(2021, 3, 16, 16, 39, tzinfo=ISTANBUL)), START)


def test_trimmed_counts_only_matching_entries_edited_before_the_range() -> None:
    run = OutletRun(get("cumhuriyet"))
    early = datetime(2023, 2, 2, tzinfo=ISTANBUL)
    late = datetime(2023, 2, 20, tzinfo=ISTANBUL)
    candidates = [
        entry(early, url="deprem-bolgesinde-1"),
        entry(early, url="dolar-rekor-kirdi-2"),
        entry(late, url="deprem-bolgesinde-3"),
    ]
    collect(run, candidates, QUERY, START, END)
    assert [row.url.rsplit("/", 1)[-1] for row in run.rows] == ["deprem-bolgesinde-3"]
    assert (run.candidates, run.trimmed, run.unconfirmed) == (3, 1, 0)


def test_sitemap_rows_are_dated_to_the_month_only() -> None:
    run = OutletRun(get("cumhuriyet"))
    collect(run, [entry(datetime(2023, 2, 20, tzinfo=ISTANBUL))], QUERY, START, END)
    [row] = run.rows
    assert (row.month, row.day) == (FEB, None)


def test_search_results_outside_the_range_are_trimmed() -> None:
    run = OutletRun(get("milliyet"))
    days = [date(2023, 2, 9), date(2023, 2, 10), date(2023, 2, 28), date(2023, 3, 1)]
    collect(run, [result(day, f"deprem-{n}") for n, day in enumerate(days)], QUERY, START, END)
    assert [row.day for row in run.rows] == [date(2023, 2, 10), date(2023, 2, 28)]
    assert [row.month for row in run.rows] == [FEB, FEB]
    assert (run.candidates, run.trimmed) == (4, 2)
