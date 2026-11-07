"""Live check (weekly CI only): fetch still reads each outlet's articles, and finds wire copies.

Run with ``uv run pytest -m live tests/live --no-cov``. It reads about 27 article pages politely:
robots.txt obeyed, the honest User-Agent, one request per second per site.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime, timedelta

import pandas as pd
import pytest

from tr_news_scraper import fetch
from tr_news_scraper._http import Http
from tr_news_scraper.outlets import Month, MonthlySitemap, builtin
from tr_news_scraper.outlets._dates import ISTANBUL
from tr_news_scraper.outlets._scan import scan

PER_OUTLET = 3
MIN_SHARE = 0.9
MIN_CHARACTERS = 300
# Probed on 2026-11-08: Cumhuriyet and TRT Haber ran the same wire copy of these three stories.
COPIES = [
    (
        "https://www.cumhuriyet.com.tr/dunya/abdde-deprem-bolgesi-icin-yardim-toplandi-2049437",
        "https://www.trthaber.com/haber/dunya/abdde-deprem-bolgesi-icin-yardim-toplandi-744447.html",
    ),
    (
        "https://www.cumhuriyet.com.tr/dunya/"
        "avrupa-parlamentosu-vekilleri-deprem-bolgesini-ziyaret-etti-2054399",
        "https://www.trthaber.com/haber/dunya/"
        "avrupa-parlamentosu-vekilleri-deprem-bolgesini-ziyaret-etti-748236.html",
    ),
    (
        "https://www.cumhuriyet.com.tr/dunya/"
        "almanya-depremzedelere-vize-kolayligi-saglamayi-planliyor-2050837",
        "https://www.trthaber.com/haber/dunya/"
        "almanya-depremzedelere-vize-kolayligi-saglamayi-planliyor-745530.html",
    ),
]


@pytest.fixture(scope="module")
def http() -> Iterator[Http]:
    client = Http()
    yield client
    client.close()


def today() -> date:
    return datetime.now(ISTANBUL).date()


def newest(http: Http) -> pd.DataFrame:
    """The newest three articles in last month's archive of each outlet; for Milliyet, its
    first three search results for "deprem" this week."""
    last_month = Month.of(today()).previous()
    rows: list[tuple[str, str]] = []
    for outlet in builtin():
        if isinstance(outlet, MonthlySitemap):
            found = scan(outlet, http, last_month.start, last_month.next().start, today=today())
            candidates = sorted(
                found,
                key=lambda c: c.lastmod or datetime.min.replace(tzinfo=ISTANBUL),
                reverse=True,
            )
        else:
            week = today() - timedelta(days=7)
            found = scan(outlet, http, week, today() + timedelta(days=1), ["deprem"], today=today())
            candidates = list(found)
        rows += [(outlet.id, candidate.url) for candidate in candidates[:PER_OUTLET]]
    return pd.DataFrame(rows, columns=["outlet", "url"], dtype="string")


@pytest.mark.live
def test_at_least_nine_in_ten_articles_give_a_headline_a_date_and_text(http: Http) -> None:
    fetched = fetch(newest(http))
    articles = pd.concat([fetched.articles, fetched.outside], ignore_index=True)
    complete = (
        articles["title"].notna()
        & articles["published"].notna()
        & (articles["text"].str.len() >= MIN_CHARACTERS).fillna(False)
    )
    print(fetched)
    missing = articles.loc[~complete, ["outlet", "url", "error"]].to_dict("records")
    assert complete.mean() >= MIN_SHARE, missing


@pytest.mark.live
def test_three_wire_stories_each_form_one_copy_group() -> None:
    urls = [url for pair in COPIES for url in pair]
    outlets = ["cumhuriyet" if "cumhuriyet" in url else "trt-haber" for url in urls]
    fetched = fetch(pd.DataFrame({"outlet": outlets, "url": urls}, dtype="string"))
    groups = dict(zip(fetched.articles["url"], fetched.articles["copy_group"], strict=True))
    for first, second in COPIES:
        assert pd.notna(groups[first]), first
        assert groups[first] == groups[second], (first, second)
    assert len({groups[first] for first, _ in COPIES}) == len(COPIES)
