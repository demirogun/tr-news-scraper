"""Live check (weekly CI only): fetch still reads each outlet's articles, and finds wire copies.

Run with ``uv run pytest -m live tests/live --no-cov``. It reads the three newest articles of every
built-in outlet, about 80 pages, each downloaded once, politely: robots.txt obeyed, the honest
User-Agent, one request per second per site. A failure names outlets, URLs and counts, never
text from the pages.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import pandas as pd
import pytest

from tr_news_scraper import fetch
from tr_news_scraper._extract import Extracted, extract
from tr_news_scraper._http import CachePolicy, Http
from tr_news_scraper._structured import PageFacts, alike, read_page
from tr_news_scraper.errors import HttpError
from tr_news_scraper.outlets import Month, SiteSearch, builtin, get
from tr_news_scraper.outlets._dates import ISTANBUL
from tr_news_scraper.outlets._scan import HTML_ACCEPT, describe, scan

PER_OUTLET = 3
MIN_SHARE = 0.9
MIN_OF_THREE = 2
MIN_CHARACTERS = 300
FURNITURE_WORDS = 5
"""A line this long or longer that every page of an outlet repeats is page furniture."""
WITHOUT_JSON_LD = {"sputnik-tr"}
"""Outlets whose pages carry no JSON-LD article: Sputnik Türkiye's are dated by their
article:published_time tag."""
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


@dataclass(frozen=True)
class Page:
    """One sampled article: what fetch extracted, and what the page states."""

    outlet: str
    url: str
    found: Extracted
    facts: PageFacts

    @property
    def complete(self) -> bool:
        text = self.found.text or ""
        return bool(self.found.title and self.found.published and len(text) >= MIN_CHARACTERS)


@pytest.fixture(scope="module")
def http() -> Iterator[Http]:
    client = Http()
    yield client
    client.close()


def today() -> date:
    return datetime.now(ISTANBUL).date()


def newest(http: Http) -> list[tuple[str, str]]:
    """The newest three articles in last month's archive of each built-in outlet; for Milliyet,
    its first three search results for "deprem" this week."""
    last_month = Month.of(today()).previous()
    rows: list[tuple[str, str]] = []
    for outlet in builtin(include_opt_in=True):
        if isinstance(outlet, SiteSearch):
            week = today() - timedelta(days=7)
            found = scan(outlet, http, week, today() + timedelta(days=1), ["deprem"], today=today())
            candidates = list(found)
        else:
            found = scan(outlet, http, last_month.start, last_month.next().start, today=today())
            candidates = sorted(
                found,
                key=lambda c: c.lastmod or datetime.min.replace(tzinfo=ISTANBUL),
                reverse=True,
            )
        rows += [(outlet.id, candidate.url) for candidate in candidates[:PER_OUTLET]]
    return rows


@pytest.fixture(scope="module")
def pages(http: Http) -> list[Page]:
    """Every sampled article, downloaded once and read both ways."""
    read: list[Page] = []
    for outlet_id, url in newest(http):
        outlet = get(outlet_id)
        try:
            page = http.get(
                url,
                allowed_hosts=outlet.hosts,
                accept=HTML_ACCEPT,
                cache=CachePolicy(no_store=True),
            )
        except HttpError as error:
            read.append(Page(outlet_id, url, Extracted(error=describe(error)), PageFacts()))
            continue
        html = page.text()
        read.append(Page(outlet_id, url, extract(html, page.url, outlet.name), read_page(html)))
    return read


def by_outlet(pages: list[Page]) -> dict[str, list[Page]]:
    grouped: defaultdict[str, list[Page]] = defaultdict(list)
    for page in pages:
        grouped[page.outlet].append(page)
    return grouped


@pytest.mark.live
def test_pages_give_a_headline_a_time_and_text_overall_and_outlet_by_outlet(
    pages: list[Page],
) -> None:
    missing = [(p.outlet, p.url, p.found.error) for p in pages if not p.complete]
    assert sum(p.complete for p in pages) >= MIN_SHARE * len(pages), missing
    short = {
        outlet: sum(p.complete for p in sampled)
        for outlet, sampled in by_outlet(pages).items()
        if sum(p.complete for p in sampled) < min(MIN_OF_THREE, len(sampled))
    }
    assert short == {}, missing
    assert {outlet.id for outlet in builtin(include_opt_in=True)} <= set(by_outlet(pages))


@pytest.mark.live
def test_json_ld_gives_the_article_on_two_of_each_outlets_three_pages(pages: list[Page]) -> None:
    # Otherwise fetch would fall back without anyone noticing.
    without = {
        outlet: sum(not p.facts.article for p in sampled)
        for outlet, sampled in by_outlet(pages).items()
        if outlet not in WITHOUT_JSON_LD
        and sum(p.facts.article for p in sampled) < min(MIN_OF_THREE, len(sampled))
    }
    assert without == {}


@pytest.mark.live
def test_headlines_and_times_are_what_the_pages_state(pages: list[Page]) -> None:
    other_headline = [
        (p.outlet, p.url)
        for p in pages
        if p.found.title
        and (p.facts.headline or p.facts.h1s)
        and p.found.title not in {p.facts.headline, *p.facts.h1s}
    ]
    other_time = [
        (p.outlet, p.url)
        for p in pages
        if p.facts.published
        and p.found.published
        and p.found.published.replace(second=0, microsecond=0)
        != p.facts.published.replace(second=0, microsecond=0)
    ]
    assert (other_headline, other_time) == ([], [])


@pytest.mark.live
def test_a_lead_the_page_shows_is_in_the_text(pages: list[Page]) -> None:
    without = [
        (p.outlet, p.url)
        for p in pages
        if p.facts.lead
        and p.found.text
        and p.facts.lead not in p.found.text
        and not any(alike(p.facts.lead, line) for line in p.found.text.split("\n"))
    ]
    assert without == []


@pytest.mark.live
def test_no_line_repeats_on_every_page_of_an_outlet(pages: list[Page]) -> None:
    # Such a line would be page furniture (a share prompt, a sign-up line) leaking into texts.
    # Only the outlet and how many lines are named: never the lines.
    repeated: dict[str, int] = {}
    for outlet, sampled in by_outlet(pages).items():
        texts = [p.found.text for p in sampled if p.found.text]
        if len(texts) < PER_OUTLET:
            continue
        lines = [
            {line for line in text.split("\n") if len(line.split()) >= FURNITURE_WORDS}
            for text in texts
        ]
        common = set.intersection(*lines)
        if common:
            repeated[outlet] = len(common)
    assert repeated == {}


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
