"""Speed budget: a year of one outlet's archive is about 100,000 candidates."""

from __future__ import annotations

import time
from datetime import date, datetime

import pandas  # noqa: F401 - imported up front, so the one-time import cost is not timed
import pytest

from tests.matching.test_performance import candidates
from tr_news_scraper._search import collect
from tr_news_scraper._table import OutletRun, build_result
from tr_news_scraper.matching import KeywordQuery
from tr_news_scraper.outlets import Candidate, Month, get
from tr_news_scraper.outlets._dates import ISTANBUL

FEB = Month(2023, 2)
# One keyword, like most searches: a third of these synthetic candidates match. With all five
# hazard words, 93% match and it takes about twice as long (2.1 s on 2026-11-08), which leaves
# too little margin for CI runners, about twice as slow as a desktop.
KEYWORDS = ("deprem",)
SOURCE = "https://www.star.com.tr/sitemaps/posts-2023-02.xml"


# The budget is for search as users run it. Before Python 3.14, coverage traces every line and
# slows this loop by about half, so coverage is paused, as for the matcher's own budget.
@pytest.mark.no_cover
def test_100k_candidates_are_matched_and_tabulated_in_under_3_seconds() -> None:
    edited = datetime(2023, 2, 14, 9, 30, tzinfo=ISTANBUL)
    archive = [
        Candidate(outlet="star", url=url, month=FEB, title=title, lastmod=edited, source=SOURCE)
        for title, url in candidates(100_000)
    ]
    star = get("star")
    run = OutletRun(star)
    started = time.perf_counter()
    collect(run, archive, KeywordQuery(KEYWORDS), date(2023, 2, 1), date(2023, 3, 1))
    result = build_result(
        [run],
        keywords=KEYWORDS,
        start=date(2023, 2, 1),
        end=date(2023, 3, 1),
        outlets=(star,),
        searched_at=edited,
        version="test",
        stats={},
    )
    elapsed = time.perf_counter() - started
    assert len(result.articles) > 30_000
    assert elapsed < 3.0, f"took {elapsed:.2f} s for {len(result.articles):,} articles"
