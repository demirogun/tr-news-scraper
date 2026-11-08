"""What search raises when nothing could be read."""

from __future__ import annotations

import logging
from datetime import datetime

import pytest
from requests_mock import Mocker

from tests.search.conftest import serve_archive
from tr_news_scraper._http import Http
from tr_news_scraper._search import _search
from tr_news_scraper._table import SearchResult
from tr_news_scraper.errors import SearchFailed, TrNewsError
from tr_news_scraper.outlets import MonthlySitemap, get
from tr_news_scraper.outlets._dates import ISTANBUL


def test_search_failed_names_every_outlet_and_its_reason() -> None:
    failures = {
        "cumhuriyet": "its sitemap index couldn't be read: the site refused it with HTTP 403",
        "milliyet": "none of the files it needed could be read",
    }
    error = SearchFailed(failures)
    assert isinstance(error, TrNewsError)
    assert error.failures == failures
    assert str(error) == (
        "every outlet failed:\n"
        "  cumhuriyet: its sitemap index couldn't be read: the site refused it with HTTP 403\n"
        "  milliyet: none of the files it needed could be read"
    )


def test_search_failed_can_say_what_to_do_next() -> None:
    error = SearchFailed({"star": "none of the files it needed could be read"}, hint="Try again.")
    assert str(error).endswith("could be read\nTry again.")


NOW = datetime(2026, 11, 7, 12, 0, tzinfo=ISTANBUL)
REFUSED = "its sitemap index couldn't be read: the site refused it with HTTP 403"


def refuse_index(requests_mock: Mocker, outlet_id: str) -> None:
    outlet = get(outlet_id)
    assert isinstance(outlet, MonthlySitemap)
    requests_mock.get(outlet.index, status_code=403)


def run(http: Http, outlets: list[str], *, offline: bool = False) -> SearchResult:
    return _search(
        "deprem",
        "2023-02-01",
        "2023-03-01",
        outlets=outlets,
        http=http,
        now=NOW,
        offline=offline,
    )


def test_when_every_outlet_fails_search_raises_with_each_reason(
    http: Http, requests_mock: Mocker
) -> None:
    refuse_index(requests_mock, "star")
    refuse_index(requests_mock, "aksam")
    with pytest.raises(SearchFailed) as failure:
        run(http, ["star", "aksam"])
    assert failure.value.failures == {"star": REFUSED, "aksam": REFUSED}


def test_offline_with_nothing_cached_says_to_search_online_once(
    http: Http, requests_mock: Mocker
) -> None:
    with pytest.raises(SearchFailed, match="search once without offline=True") as failure:
        run(http, ["star"], offline=True)
    assert failure.value.failures == {
        "star": "its sitemap index couldn't be read: it isn't in the cache (offline mode)"
    }
    assert requests_mock.call_count == 0


def test_when_only_some_outlets_fail_the_result_is_returned(
    http: Http, requests_mock: Mocker, caplog: pytest.LogCaptureFixture
) -> None:
    serve_archive(requests_mock, "cumhuriyet")
    refuse_index(requests_mock, "star")
    with caplog.at_level(logging.INFO, logger="tr_news_scraper.search"):
        result = run(http, ["cumhuriyet", "star"])
    assert list(result.report["status"]) == ["ok", "failed"]
    assert list(result.report["detail"]) == ["", REFUSED]
    assert len(result.articles) == 6
    logged = {(r.levelname, r.getMessage()) for r in caplog.records if r.name.endswith("search")}
    assert logged == {
        ("INFO", "Cumhuriyet: 6 matching articles among 20 candidates, 0 gap(s)"),
        ("WARNING", f"Star failed: {REFUSED}"),
    }


@pytest.mark.parametrize("keyword", ["a", '""', "*"])
def test_an_invalid_keyword_is_refused_before_any_request(
    http: Http, requests_mock: Mocker, keyword: str
) -> None:
    with pytest.raises(ValueError, match="keyword"):
        _search(
            [keyword],
            "2023-02-01",
            "2023-03-01",
            outlets=None,
            http=http,
            now=NOW,
            offline=False,
        )
    assert requests_mock.call_count == 0
