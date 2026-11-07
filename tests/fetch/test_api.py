"""The public fetch(): from a search result to the articles' text, and what it raises."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any, cast

import pytest
from requests_mock import Mocker

import tr_news_scraper
import tr_news_scraper._fetch as fetch_module
from tests.fetch.conftest import serve_page
from tests.search.conftest import TODAY, serve_archive
from tr_news_scraper import FetchResult, fetch
from tr_news_scraper._fetch import _fetch
from tr_news_scraper._http import Http
from tr_news_scraper._search import _search
from tr_news_scraper._table import SearchResult, articles_frame
from tr_news_scraper.errors import FetchFailed
from tr_news_scraper.outlets._dates import ISTANBUL

NOW = datetime(2026, 11, 8, 12, 0, tzinfo=ISTANBUL)
SEARCHED = datetime.combine(TODAY, datetime.min.time(), ISTANBUL)


def fetched(http: Http, articles: object, **options: Any) -> FetchResult:
    settings: dict[str, Any] = {
        "start": None,
        "end": None,
        "outlets": None,
        "progress": None,
        "offline": False,
        "refresh": False,
    }
    return _fetch(articles, http=http, now=NOW, **{**settings, **options})  # type: ignore[arg-type]


def test_fetch_reads_every_article_a_search_found(http: Http, requests_mock: Mocker) -> None:
    serve_archive(requests_mock, "star")
    found = _search(
        "deprem",
        "2023-02-01",
        "2023-03-01",
        outlets=["star"],
        http=http,
        now=SEARCHED,
        offline=False,
    )
    for url in found.articles["url"]:
        serve_page(requests_mock, str(url), "star")
    result = fetched(http, found)
    assert len(result.articles) == 4
    assert result.articles["error"].isna().all()
    assert set(result.articles["author"]) == {"IHA"}
    assert set(result.articles["text_matched"]) == {"deprem"}
    assert result.articles["copy_group"].tolist() == [1, 1, 1, 1]  # one skeleton served four times
    assert (result.keywords, result.start, result.end) == (found.keywords, found.start, found.end)
    assert str(result).startswith("deprem, 2023-02-01 to 2023-02-28: 4 articles read")


def test_a_search_result_brings_its_own_range_and_outlets(http: Http) -> None:
    empty = articles_frame([])
    found = SearchResult(
        empty, empty, empty, ("deprem",), date(2023, 2, 1), date(2023, 3, 1), (), SEARCHED, "1"
    )
    with pytest.raises(
        ValueError, match="a SearchResult brings its own keywords, range and outlets"
    ):
        fetched(http, found, start="2023-02-01", end="2023-03-01")
    with pytest.raises(
        ValueError, match="a SearchResult brings its own keywords, range and outlets"
    ):
        fetched(http, found, outlets=["star"])
    with pytest.raises(
        ValueError, match="a SearchResult brings its own keywords, range and outlets"
    ):
        fetched(http, found, keywords=["sel"])


def test_when_nothing_could_be_read_fetch_fails_with_each_outlets_reason(
    http: Http, requests_mock: Mocker
) -> None:
    import pandas as pd

    url = "https://www.star.com.tr/yasam/a-haber-1/"
    requests_mock.get(url, status_code=403)
    rows = pd.DataFrame({"outlet": ["star"], "url": [url]}, dtype="string")
    with pytest.raises(FetchFailed) as failure:
        fetched(http, rows)
    assert failure.value.failures == {"star": "the site refused it with HTTP 403"}


def test_offline_with_nothing_cached_says_to_fetch_online_once(
    http: Http, requests_mock: Mocker
) -> None:
    import pandas as pd

    rows = pd.DataFrame({"outlet": ["star"], "url": ["https://www.star.com.tr/a/"]}, dtype="string")
    with pytest.raises(FetchFailed, match="fetch once without offline=True"):
        fetched(http, rows, offline=True)
    assert requests_mock.call_count == 0


def test_the_public_fetch_builds_one_polite_client_from_its_settings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen: dict[str, Any] = {}
    marker = cast(FetchResult, object())

    def fake(articles: object, **kwargs: Any) -> FetchResult:
        seen.update(kwargs, articles=articles, config=kwargs["http"].config)
        return marker

    monkeypatch.setattr(fetch_module, "_fetch", fake)
    progress = print
    assert (
        fetch(
            "table",  # type: ignore[arg-type]
            start="2023-02-01",
            end="2023-03-01",
            outlets=["star"],
            progress=progress,
            contact="mailto:lab@example.org",
            obey_robots=False,
            offline=True,
            refresh=True,
            cache_dir=tmp_path,
        )
        is marker
    )
    config = seen["config"]
    assert (config.contact, config.obey_robots, config.cache_dir) == (
        "mailto:lab@example.org",
        False,
        tmp_path,
    )
    assert (seen["articles"], seen["start"], seen["end"], seen["outlets"]) == (
        "table",
        "2023-02-01",
        "2023-03-01",
        ["star"],
    )
    assert (seen["progress"], seen["offline"], seen["refresh"]) == (progress, True, True)
    assert seen["now"].tzinfo is ISTANBUL


def test_the_package_exports_fetch_and_its_result() -> None:
    assert {"fetch", "FetchResult"} <= set(tr_news_scraper.__all__)
    assert tr_news_scraper.fetch is fetch
