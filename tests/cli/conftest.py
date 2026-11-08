"""Tables and stand-ins for the CLI's tests: results shaped like search's and fetch's."""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import pandas as pd
import pytest

from tr_news_scraper import _cli
from tr_news_scraper._fetched import FetchResult
from tr_news_scraper._table import (
    ARTICLE_COLUMNS,
    SearchResult,
    day_series,
    string_series,
    time_series,
)
from tr_news_scraper.outlets import get
from tr_news_scraper.outlets._dates import ISTANBUL

HAS_PYARROW = importlib.util.find_spec("pyarrow") is not None
LINES = 'Birinci satır, virgüllü.\nİkinci satır; noktalı virgüllü ve "tırnaklı".'
OUTLETS = (get("aksam"), get("sozcu"), get("star"))


def fetched_table() -> pd.DataFrame:
    """Search's columns plus fetch's, with every type, empty values and awkward text."""
    return pd.DataFrame(
        {
            "outlet": string_series(["aksam", "sozcu", "star"]),
            "month": string_series(["2023-02", "2023-02", "2023-02"]),
            "day": day_series([date(2023, 2, 6), None, date(2023, 2, 7)]),
            "title": string_series(["Akşam'da deprem", None, '=HYPERLINK("http://x", "x")']),
            "url": string_series(
                [
                    "https://www.aksam.com.tr/guncel/deprem/haber-1",
                    "https://www.sozcu.com.tr/deprem-2",
                    "https://www.star.com.tr/guncel/deprem-3",
                ]
            ),
            "matched": string_series(["deprem", "deprem, tsunami", "deprem"]),
            "reasons": string_series(["title", "url", "title"]),
            "lastmod": time_series([datetime(2023, 2, 6, 4, 17, tzinfo=ISTANBUL), None, None]),
            "source": string_series(["sitemap", "sitemap", "sitemap"]),
            "published": time_series([datetime(2023, 2, 6, 4, 2, tzinfo=ISTANBUL), None, None]),
            "author": string_series(["Ayşe Demir", None, "'=x"]),
            "text": string_series([LINES, None, "-15 derece"]),
            "text_matched": string_series(["deprem", "", ""]),
            "copy_group": pd.Series([1, None, 1], dtype="Int64"),
            "fetched_at": time_series(
                [datetime(2026, 11, 8, 14, 3, 12, 345678, tzinfo=ISTANBUL), None, None]
            ),
            "error": string_series([None, "HTTP 404", None]),
        }
    )


def search_result(detail: str = "") -> SearchResult:
    """Three articles from three outlets in February 2023; Akşam's report says ``detail``."""
    return SearchResult(
        articles=fetched_table()[list(ARTICLE_COLUMNS)],
        report=pd.DataFrame(
            {
                "outlet": string_series(["aksam", "sozcu", "star"]),
                "name": string_series(["Akşam", "Sözcü", "Star"]),
                "status": string_series(["ok", "ok", "ok"]),
                "articles": pd.Series([1, 1, 1], dtype="int64"),
                "detail": string_series([detail, "", ""]),
            }
        ),
        gaps=pd.DataFrame(
            {
                "outlet": string_series(["sozcu"]),
                "reason": string_series(["before-archive"]),
                "month": string_series(["2023-02"]),
                "detail": string_series(["Sözcü's archive starts in 2023-12"]),
            }
        ),
        keywords=("deprem", "tsunami"),
        start=date(2023, 2, 1),
        end=date(2023, 3, 1),
        outlets=OUTLETS,
        searched_at=datetime(2026, 11, 8, 14, 0, tzinfo=ISTANBUL),
        version="1.0.0",
    )


def fetch_result() -> FetchResult:
    """What fetch read from search_result(): Sözcü's page failed, Star's is dated outside."""
    table = fetched_table()
    return FetchResult(
        articles=table.iloc[:2].reset_index(drop=True),
        outside=table.iloc[2:].reset_index(drop=True),
        report=pd.DataFrame(
            {
                "outlet": string_series(["aksam", "sozcu", "star"]),
                "name": string_series(["Akşam", "Sözcü", "Star"]),
                "failed": pd.Series([0, 1, 0], dtype="int64"),
                "detail": string_series(["", "1 × HTTP 404", ""]),
            }
        ),
        keywords=("deprem", "tsunami"),
        start=date(2023, 2, 1),
        end=date(2023, 3, 1),
        outlets=OUTLETS,
        fetched_at=datetime(2026, 11, 8, 15, 0, tzinfo=ISTANBUL),
        version="1.0.0",
    )


@dataclass
class Library:
    """Stand-ins for search() and fetch(): what they were called with, and what they do."""

    searches: list[dict[str, Any]] = field(default_factory=list)
    fetches: list[dict[str, Any]] = field(default_factory=list)
    on_search: Callable[[], SearchResult] = search_result
    on_fetch: Callable[[Any], FetchResult] = lambda progress: fetch_result()

    def search(self, keywords: Any, start: Any, end: Any, **options: Any) -> SearchResult:
        self.searches.append({"keywords": keywords, "start": start, "end": end, **options})
        return self.on_search()

    def fetch(self, articles: Any, **options: Any) -> FetchResult:
        self.fetches.append({"articles": articles, **options})
        return self.on_fetch(options["progress"])


@pytest.fixture
def library(monkeypatch: pytest.MonkeyPatch) -> Library:
    """Replace search() and fetch() in the CLI with stand-ins."""
    stand_ins = Library()
    monkeypatch.setattr(_cli, "search", stand_ins.search)
    monkeypatch.setattr(_cli, "fetch", stand_ins.fetch)
    return stand_ins
