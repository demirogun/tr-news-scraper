"""coverage(): each outlet's archive, offline by default, or checked live (S10)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, cast

import pandas as pd
import pytest
from requests_mock import Mocker

import tr_news_scraper
import tr_news_scraper._coverage as coverage_module
from tests.search.conftest import recorded, serve_archive, serve_milliyet
from tr_news_scraper import coverage
from tr_news_scraper._coverage import COVERAGE_COLUMNS, HEALTH_COLUMNS, _coverage
from tr_news_scraper._http import Http
from tr_news_scraper.outlets import builtin, get
from tr_news_scraper.outlets._dates import ISTANBUL

NOW = datetime(2026, 11, 7, 12, 0, tzinfo=ISTANBUL)
CUMHURIYET_LAST_MONTH = "https://www.cumhuriyet.com.tr/sitemaps/posts-2026-10.xml"


def test_coverage_lists_every_built_in_outlet_without_a_request(requests_mock: Mocker) -> None:
    table = coverage()
    assert requests_mock.call_count == 0
    assert tuple(table.columns) == COVERAGE_COLUMNS
    assert {str(dtype) for dtype in table.dtypes} == {"string"}
    assert list(table["outlet"]) == [outlet.id for outlet in builtin()]
    rows = table.set_index("outlet")
    assert tuple(rows.loc["star", ["method", "earliest", "headlines", "hosts"]]) == (
        "monthly sitemap",
        "2012-09",
        "image titles",
        "www.star.com.tr",
    )
    assert rows.loc["cumhuriyet", "headlines"] == "no"
    assert tuple(rows.loc["milliyet", ["method", "headlines"]]) == ("site search", "search results")
    assert table["earliest"].isna().tolist() == [False] * 6 + [True]
    assert rows.loc["sozcu", "notes"] == get("sozcu").notes


def test_coverage_keeps_the_order_of_the_outlets_given() -> None:
    assert list(coverage(["milliyet", "star"])["outlet"]) == ["milliyet", "star"]


def test_a_live_check_reads_two_files_or_pages_per_outlet(
    http: Http, requests_mock: Mocker
) -> None:
    serve_archive(requests_mock, "cumhuriyet")
    requests_mock.get(CUMHURIYET_LAST_MONTH, content=recorded("cumhuriyet", "2023-02.xml"))
    serve_milliyet(requests_mock)
    table = _coverage((get("cumhuriyet"), get("milliyet")), http, now=NOW)
    assert tuple(table.columns) == (*COVERAGE_COLUMNS, *HEALTH_COLUMNS)
    assert str(table["ok"].dtype) == "bool"
    assert str(table["sample"].dtype) == "int64"
    assert str(table["checked_at"].dtype) == "datetime64[ns, Europe/Istanbul]"
    rows = table.set_index("outlet")
    assert tuple(rows.loc["cumhuriyet", ["ok", "problems", "oldest", "newest", "sample"]]) == (
        True,
        "",
        "1962-08",
        "2026-11",
        20,
    )
    assert bool(rows.loc["milliyet", "ok"]) is False
    assert rows.loc["milliyet", "problems"] == (
        "page 1 for 'deprem' has 5 complete results; at least 10 were expected"
    )
    assert table["oldest"].isna().tolist() == [False, True]
    assert set(table["checked_at"]) == {pd.Timestamp(NOW)}
    archive = [r for r in requests_mock.request_history if not r.url.endswith("/robots.txt")]
    assert sorted({r.hostname for r in archive}) == ["www.cumhuriyet.com.tr", "www.milliyet.com.tr"]
    assert all(
        sum(r.hostname == host for r in archive) == 2 for host in {r.hostname for r in archive}
    )


def test_coverage_builds_a_client_only_for_a_live_check(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen: list[Any] = []
    marker = cast(pd.DataFrame, object())

    def fake(outlets: object, http: Http | None, *, now: datetime) -> pd.DataFrame:
        seen.append((outlets, None if http is None else http.config, now))
        return marker

    monkeypatch.setattr(coverage_module, "_coverage", fake)
    assert coverage("star") is marker
    assert (
        coverage(["star"], check=True, contact="mailto:lab@example.org", cache_dir=tmp_path)
        is marker
    )
    (first, no_client, _), (second, config, now) = seen
    assert first == second == (get("star"),)
    assert no_client is None
    assert (config.contact, config.obey_robots, config.cache_dir) == (
        "mailto:lab@example.org",
        True,
        tmp_path,
    )
    assert now.tzinfo is ISTANBUL


def test_the_package_exports_coverage() -> None:
    assert "coverage" in tr_news_scraper.__all__
    assert tr_news_scraper.coverage is coverage
