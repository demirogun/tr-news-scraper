"""One outlet's run: matching its candidates, normalizing them, and keeping its gaps (S3, S5)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

from requests_mock import Mocker

from tests.search.conftest import TODAY, serve_archive, serve_milliyet
from tr_news_scraper._http import Http
from tr_news_scraper._search import collect, run_outlet
from tr_news_scraper._table import OutletRun, clean_title, clean_url
from tr_news_scraper.matching import KeywordQuery
from tr_news_scraper.outlets import Candidate, Month, MonthlySitemap, get
from tr_news_scraper.outlets._dates import ISTANBUL

FEB = Month(2023, 2)
FEB_START, MAR_START = date(2023, 2, 1), date(2023, 3, 1)
SOURCE = "https://www.star.com.tr/sitemaps/posts-2023-02.xml"


def star(url: str, title: str | None = None, lastmod: datetime | None = None) -> Candidate:
    return Candidate(
        outlet="star",
        url=f"https://www.star.com.tr/{url}",
        month=FEB,
        title=title,
        lastmod=lastmod,
        source=SOURCE,
    )


def test_a_match_keeps_its_keywords_in_query_order_and_every_reason() -> None:
    run = OutletRun(get("star"))
    candidate = star("guncel/deprem-ve-sel-uyarisi-haber-1/", title="Depremin ardından sel")
    collect(run, [candidate], KeywordQuery(["sel", "deprem"]), FEB_START, MAR_START)
    [row] = run.rows
    assert row.matched == ("sel", "deprem")
    assert row.reasons == (
        "title: 'sel' matches 'sel' (stem)",
        "title: 'depremin' matches 'deprem' (prefix)",
        "url: 'sel' matches 'sel' (stem)",
        "url: 'deprem' matches 'deprem' (prefix)",
    )
    assert (row.outlet, row.title, row.source) == ("star", "Depremin ardından sel", SOURCE)


def test_a_headline_can_match_when_the_url_does_not() -> None:
    run = OutletRun(get("star"))
    collect(
        run,
        [star("spor/gokhan-tore-haber-1770642/", title="Gökhan Töre depremi!")],
        KeywordQuery(["deprem"]),
        FEB_START,
        MAR_START,
    )
    assert [row.reasons for row in run.rows] == [("title: 'depremi' matches 'deprem' (prefix)",)]


def test_unmatched_sitemap_entries_only_count_as_candidates() -> None:
    run = OutletRun(get("star"))
    collect(run, [star("ekonomi/dolar-haber-1/")], KeywordQuery(["deprem"]), FEB_START, MAR_START)
    assert (run.rows, run.candidates, run.trimmed, run.unconfirmed) == ([], 1, 0, 0)


def test_unmatched_search_results_count_as_unconfirmed() -> None:
    run = OutletRun(get("milliyet"))
    other = Candidate(
        outlet="milliyet",
        url="https://www.milliyet.com.tr/gundem/afad-aciklama-yapti-7000001",
        month=FEB,
        title="AFAD açıklama yaptı",
        day=date(2023, 2, 6),
    )
    collect(run, [other], KeywordQuery(["deprem"]), FEB_START, MAR_START)
    assert (run.rows, run.candidates, run.unconfirmed) == ([], 1, 1)


def test_rows_hold_normalized_urls_titles_and_times() -> None:
    run = OutletRun(get("star"))
    edited = datetime(2023, 2, 28, 19, 46, tzinfo=timezone(timedelta(hours=1)))
    candidate = Candidate(
        outlet="star",
        url="HTTPS://WWW.Star.com.tr:443/guncel/deprem-haber-1/#yorumlar",
        month=FEB,
        title="  ÖSYM&#39;den  deprem\u00a0bölgeleri &amp; yeni karar ",
        lastmod=edited,
    )
    collect(run, [candidate], KeywordQuery(["deprem"]), FEB_START, MAR_START)
    [row] = run.rows
    assert row.url == "https://www.star.com.tr/guncel/deprem-haber-1/"
    assert row.title == "ÖSYM'den deprem bölgeleri & yeni karar"
    assert row.lastmod == edited
    assert row.lastmod is not None
    assert row.lastmod.tzinfo is ISTANBUL


def test_clean_url_keeps_the_path_query_and_any_other_port() -> None:
    assert clean_url(" https://Example.COM.tr:8443/A/B?x=1&Y=2#top ") == (
        "https://example.com.tr:8443/A/B?x=1&Y=2"
    )
    assert clean_url("https://www.example.com.tr:99999/a") == "https://www.example.com.tr:99999/a"


def test_clean_title_turns_an_empty_title_into_none() -> None:
    assert clean_title("  \t ") is None
    assert clean_title(None) is None
    assert clean_title("Cafe\u0301") == "Café"


def test_a_recorded_month_yields_its_deprem_entries(http: Http, requests_mock: Mocker) -> None:
    serve_archive(requests_mock, "cumhuriyet")
    run = run_outlet(
        get("cumhuriyet"),
        http,
        KeywordQuery(["deprem"]),
        FEB_START,
        MAR_START,
        today=TODAY,
        offline=False,
    )
    assert (run.candidates, len(run.rows), run.trimmed) == (20, 6, 0)
    assert (run.gaps, run.failure) == ([], None)
    assert {row.month for row in run.rows} == {FEB}
    assert run.rows[0].url == (
        "https://www.cumhuriyet.com.tr/siyaset/depremin-sorumlularinin-belirlenmesi-hakkindaki-"
        "onerge-akp-ve-mhp-oylariyla-reddedildi-2056359"
    )


def test_aksams_older_entries_in_a_february_file_stay(http: Http, requests_mock: Mocker) -> None:
    serve_archive(requests_mock, "aksam")
    run = run_outlet(
        get("aksam"),
        http,
        KeywordQuery(["deprem"]),
        date(2023, 2, 10),
        MAR_START,
        today=TODAY,
        offline=False,
    )
    assert (len(run.rows), run.trimmed) == (6, 0)
    assert {row.lastmod.year for row in run.rows if row.lastmod} == {2021, 2022, 2023}


def test_a_failed_outlet_records_its_reason(http: Http, requests_mock: Mocker) -> None:
    outlet = get("star")
    assert isinstance(outlet, MonthlySitemap)
    requests_mock.get(outlet.index, status_code=403)
    run = run_outlet(
        get("star"),
        http,
        KeywordQuery(["deprem"]),
        FEB_START,
        MAR_START,
        today=TODAY,
        offline=False,
    )
    assert run.failure == "its sitemap index couldn't be read: the site refused it with HTTP 403"
    assert run.rows == []


def test_a_site_search_keeps_its_window_gap(http: Http, requests_mock: Mocker) -> None:
    serve_milliyet(requests_mock)
    run = run_outlet(
        get("milliyet"),
        http,
        KeywordQuery(["deprem"]),
        FEB_START,
        MAR_START,
        today=TODAY,
        offline=False,
    )
    [gap] = run.gaps
    assert (gap.reason, gap.keyword, gap.reached) == ("window", "deprem", date(2024, 5, 25))
    assert (run.rows, run.candidates, run.failure) == ([], 0, None)


def test_a_cumhuriyet_entry_in_utc_is_converted_to_istanbul() -> None:
    run = OutletRun(get("cumhuriyet"))
    candidate = Candidate(
        outlet="cumhuriyet",
        url="https://www.cumhuriyet.com.tr/turkiye/deprem-1",
        month=FEB,
        lastmod=datetime(2023, 2, 27, 21, 30, tzinfo=UTC),
    )
    collect(run, [candidate], KeywordQuery(["deprem"]), FEB_START, MAR_START)
    assert run.rows[0].lastmod == datetime(2023, 2, 28, 0, 30, tzinfo=ISTANBUL)
