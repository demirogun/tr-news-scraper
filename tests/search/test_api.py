"""The public search(): its keyword arguments become the http layer's settings."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any, cast

import pytest

import tr_news_scraper
import tr_news_scraper._search as search_module
from tr_news_scraper import SearchResult, search
from tr_news_scraper._http import Http
from tr_news_scraper.outlets._dates import ISTANBUL


def test_the_package_exports_search_and_its_result() -> None:
    assert {"search", "SearchResult"} <= set(tr_news_scraper.__all__)
    assert tr_news_scraper.search is search
    assert tr_news_scraper.SearchResult is SearchResult


def test_search_builds_one_polite_client_from_its_settings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen: dict[str, Any] = {}
    marker = cast(SearchResult, object())

    def fake(keywords: object, start: object, end: object, **kwargs: Any) -> SearchResult:
        http: Http = kwargs["http"]
        seen.update(kwargs, keywords=keywords, start=start, end=end, config=http.config)
        return marker

    monkeypatch.setattr(search_module, "_search", fake)
    found = search(
        ["deprem"],
        "2023-02-01",
        date(2023, 3, 1),
        outlets=["star"],
        contact="mailto:lab@example.org",
        obey_robots=False,
        offline=True,
        cache_dir=str(tmp_path),
    )
    assert found is marker
    config = seen["config"]
    assert (config.contact, config.obey_robots, config.cache_dir) == (
        "mailto:lab@example.org",
        False,
        tmp_path,
    )
    assert (seen["keywords"], seen["start"], seen["end"]) == (
        ["deprem"],
        "2023-02-01",
        date(2023, 3, 1),
    )
    assert (seen["outlets"], seen["offline"]) == (["star"], True)
    now: datetime = seen["now"]
    assert now.tzinfo is ISTANBUL


def test_an_unsafe_contact_is_refused_before_any_request() -> None:
    with pytest.raises(ValueError, match="contact must be printable ASCII"):
        search("deprem", "2023-02-01", "2023-03-01", contact="me; DROP")
