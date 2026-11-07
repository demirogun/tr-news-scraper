"""Success criterion 1: "deprem" in February 2023, over the outlets' recorded archives."""

from __future__ import annotations

from datetime import datetime

from requests_mock import Mocker

from tests.search.conftest import serve_every_outlet
from tr_news_scraper._http import Http
from tr_news_scraper._search import _search
from tr_news_scraper._table import SearchResult
from tr_news_scraper.outlets import builtin
from tr_news_scraper.outlets._dates import ISTANBUL

NOW = datetime(2026, 11, 7, 12, 0, tzinfo=ISTANBUL)
# The recorded month files keep 20 entries each; these many of them name "deprem".
EXPECTED = {
    "cumhuriyet": 6,
    "euronews-tr": 5,
    "trt-haber": 8,
    "star": 4,
    "aksam": 6,
    "sozcu": 0,
    "milliyet": 0,
}


def february(http: Http, requests_mock: Mocker) -> SearchResult:
    serve_every_outlet(requests_mock)
    return _search(
        ["deprem"],
        "2023-02-01",
        "2023-03-01",
        outlets=None,
        http=http,
        now=NOW,
        offline=False,
    )


def test_five_outlets_return_their_recorded_deprem_articles(
    http: Http, requests_mock: Mocker
) -> None:
    result = february(http, requests_mock)
    found = dict(zip(result.report["outlet"], result.report["articles"], strict=True))
    assert found == EXPECTED
    articles = result.articles
    assert set(articles["month"]) == {"2023-02"}
    assert set(articles["matched"]) == {"deprem"}
    assert articles["day"].isna().all()
    assert articles["url"].is_unique
    assert list(articles["outlet"].drop_duplicates()) == [
        "cumhuriyet",
        "euronews-tr",
        "trt-haber",
        "star",
        "aksam",
    ]


def test_stars_rows_carry_their_headlines(http: Http, requests_mock: Mocker) -> None:
    articles = february(http, requests_mock).articles
    star = articles[articles["outlet"] == "star"]
    assert set(star["title"]) == {
        "ÖSYM'den deprem bölgeleri hakkında yeni karar! Ücret alınmayacak",
        "Gökhan Töre depremi! Sonunda başına bu da geldi: Her şey alt üst oldu...",
        "İran'da 4,6 büyüklüğünde deprem",
        "Kayseri'de 4,4 büyüklüğünde deprem meydana geldi",
    }
    others = articles[articles["outlet"] != "star"]
    assert others["title"].isna().all()


def test_the_report_explains_the_two_outlets_without_articles(
    http: Http, requests_mock: Mocker
) -> None:
    result = february(http, requests_mock)
    report = result.report.set_index("outlet")
    assert list(report.index) == [outlet.id for outlet in builtin()]
    assert set(report["status"]) == {"ok"}
    covered = {"cumhuriyet", "euronews-tr", "trt-haber", "star", "aksam"}
    assert set(report.loc[sorted(covered), "coverage"]) == {"full"}
    assert report.loc["sozcu", "coverage"] == "none"
    assert report.loc["sozcu", "detail"] == "the archive starts in 2023-12"
    assert report.loc["sozcu", "requests"] == 2  # robots.txt and the index, nothing else
    assert report.loc["milliyet", "coverage"] == "none"
    assert str(report.loc["milliyet", "detail"]).startswith(
        "Milliyet's search has nothing older than 2024-05-25 for 'deprem'"
    )
    assert str(result).splitlines()[0] == (
        "deprem, 2023-02-01 to 2023-02-28: 29 articles from 5 of 7 outlets"
    )
