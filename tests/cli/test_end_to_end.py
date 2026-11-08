"""Success criteria 1 and 2: trnews over the recorded archives and the outlets' page skeletons.

The real library runs under ``main()``: requests go to requests-mock, and the http layer's clock
is the tests' fake clock, so its one-second pauses take no time.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from requests_mock import Mocker

from tests.fetch.conftest import serve_page
from tests.http.conftest import FakeClock
from tests.search.conftest import serve_every_outlet
from tr_news_scraper._cli import main
from tr_news_scraper._files import read_table
from tr_news_scraper._http import client
from tr_news_scraper.outlets import builtin

SEARCH = ["search", "deprem", "--from", "2023-02-01", "--to", "2023-02-28"]
FETCHED = ("published", "author", "text", "text_matched", "copy_group", "fetched_at", "error")


@pytest.fixture(autouse=True)
def _archives(requests_mock: Mocker, monkeypatch: pytest.MonkeyPatch) -> None:
    """The recorded archives on hosts without robots.txt, and pauses that take no time."""
    for host in {host for outlet in builtin() for host in outlet.hosts}:
        requests_mock.get(f"https://{host}/robots.txt", status_code=404)
    serve_every_outlet(requests_mock)
    monkeypatch.setattr(client, "SystemClock", FakeClock)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def test_search_writes_what_it_found_and_a_report_on_every_outlet(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    found = tmp_path / "found.csv"
    assert main([*SEARCH, "-o", str(found), "--cache-dir", str(tmp_path / "cache")]) == 0
    table = read_table(found)
    assert len(table) == 29
    assert table["url"].is_unique
    report = read_json(tmp_path / "found.report.json")
    assert [row["outlet"] for row in report["search"]["report"]] == [o.id for o in builtin()]
    assert (report["from"], report["to"], report["keywords"]) == (
        "2023-02-01",
        "2023-02-28",
        ["deprem"],
    )
    err = capsys.readouterr().err
    assert "\ndeprem, 2023-02-01 to 2023-02-28: 29 articles from 5 of 7 outlets\n" in err
    assert err.endswith(f" and {tmp_path / 'found.report.json'}.\n")


def test_search_fetch_gives_the_same_rows_as_search_then_fetch(
    tmp_path: Path, requests_mock: Mocker, capsys: pytest.CaptureFixture[str]
) -> None:
    cache = ["--cache-dir", str(tmp_path / "cache")]
    found = tmp_path / "found.csv"
    assert main([*SEARCH, "-q", "-o", str(found), *cache]) == 0
    for outlet, url in zip(*(read_table(found)[name] for name in ("outlet", "url")), strict=True):
        serve_page(requests_mock, str(url), str(outlet))

    together = tmp_path / "together.csv"
    assert main([*SEARCH, "--fetch", "-o", str(together), *cache]) == 0
    headline = "deprem, 2023-02-01 to 2023-02-28: 21 articles read, 8 outside the range, 0 failed"
    assert f"\n{headline}\n" in capsys.readouterr().err

    apart = tmp_path / "apart.jsonl"
    assert main(["fetch", str(found), "-o", str(apart), *cache]) == 0
    assert f"\n{headline}\n" in capsys.readouterr().err

    articles, outside = read_table(together), read_table(tmp_path / "together.outside.csv")
    assert set(FETCHED) <= set(articles.columns)
    assert len(articles) == 21
    assert articles["error"].isna().all()
    assert set(outside["outlet"]) == {"trt-haber"}
    pd.testing.assert_frame_equal(read_table(apart), articles)
    pd.testing.assert_frame_equal(read_table(tmp_path / "apart.outside.jsonl"), outside)

    one, two = (
        read_json(tmp_path / "together.report.json"),
        read_json(tmp_path / "apart.report.json"),
    )
    assert (two["input"], two["search"]) == (
        "found.csv",
        read_json(tmp_path / "found.report.json")["search"],
    )
    assert [row["articles"] for row in one["fetch"]["report"]] == [
        row["articles"] for row in two["fetch"]["report"]
    ]
