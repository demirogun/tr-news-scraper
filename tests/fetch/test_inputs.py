"""fetch()'s inputs (F1) are checked before any request."""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import pytest
from requests_mock import Mocker

from tr_news_scraper._fetch import _fetch
from tr_news_scraper._http import Http
from tr_news_scraper.outlets import MonthlySitemap
from tr_news_scraper.outlets._dates import ISTANBUL

NOW = datetime(2026, 11, 8, 12, 0, tzinfo=ISTANBUL)
ORNEK = MonthlySitemap(
    id="ornek-gazete",
    name="Örnek Gazete",
    index="https://www.example.com.tr/sitemaps/posts.xml",
    month_file=r"/sitemaps/posts-(?P<year>\d{4})-(?P<month>\d{2})\.xml$",
)


def table(**columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {name: pd.Series(values, dtype="string") for name, values in columns.items()}
    )


def check(http: Http, articles: object, **options: object) -> None:
    settings: dict[str, object] = {
        "start": None,
        "end": None,
        "outlets": None,
        "progress": None,
        "offline": False,
        "refresh": False,
    }
    _fetch(articles, http=http, now=NOW, **{**settings, **options})  # type: ignore[arg-type]


def test_a_table_needs_outlet_and_url_columns(http: Http, requests_mock: Mocker) -> None:
    with pytest.raises(ValueError, match="needs the columns outlet and url; it has: link"):
        check(http, table(link=["https://www.star.com.tr/a"]))
    assert requests_mock.call_count == 0


def test_every_row_needs_an_outlet_and_a_url(http: Http) -> None:
    rows = table(outlet=["star", "star"], url=["https://www.star.com.tr/a", None])  # type: ignore[list-item]
    with pytest.raises(ValueError, match="row 1 has no outlet or no url"):
        check(http, rows)


def test_a_range_needs_both_ends(http: Http) -> None:
    rows = table(outlet=["star"], url=["https://www.star.com.tr/a"])
    with pytest.raises(ValueError, match="give both start and end, or neither"):
        check(http, rows, start="2023-02-01")


def test_a_range_is_checked_like_searchs(http: Http) -> None:
    rows = table(outlet=["star"], url=["https://www.star.com.tr/a"])
    with pytest.raises(ValueError, match=r"the start \(2023-03-01\) must be before the end"):
        check(http, rows, start="2023-03-01", end=date(2023, 2, 1))


def test_rows_of_unknown_outlets_need_their_definitions(http: Http) -> None:
    rows = table(outlet=["star", "ornek-gazete"], url=["https://a.com.tr/1", "https://b.com.tr/2"])
    with pytest.raises(
        ValueError, match="no outlet definition for ornek-gazete; pass it in outlets"
    ):
        check(http, rows)
    with pytest.raises(ValueError, match="no outlet definition for star"):
        check(http, rows, outlets=[ORNEK])


def test_only_a_table_or_a_search_result_can_be_fetched(http: Http) -> None:
    with pytest.raises(TypeError, match="fetch takes a SearchResult or a DataFrame, not list"):
        check(http, ["https://www.star.com.tr/a"])


def test_an_empty_table_makes_no_request(http: Http, requests_mock: Mocker) -> None:
    result = _fetch(
        table(outlet=[], url=[]),
        start=None,
        end=None,
        outlets=None,
        progress=None,
        http=http,
        now=NOW,
        offline=False,
        refresh=False,
    )
    assert (len(result.articles), len(result.report)) == (0, 0)
    assert requests_mock.call_count == 0
