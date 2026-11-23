"""Live check (weekly CI only): every built-in outlet's archive still works.

Run with ``uv run pytest -m live tests/live --no-cov``. These tests read real archives politely:
robots.txt obeyed, the honest User-Agent, one request per second per site. A failure means an
outlet changed; its definition has to change too.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime

import pytest

from tr_news_scraper._http import Http
from tr_news_scraper.outlets import Month, Outlet, builtin, get
from tr_news_scraper.outlets._dates import ISTANBUL
from tr_news_scraper.outlets._health import check
from tr_news_scraper.outlets._scan import scan

FEB_2023 = Month(2023, 2)
# About half of what each reference month held when its outlet was added (1.0's on 2026-11-07,
# 1.1's on 2026-11-23): deleting some articles won't trip the check, a broken archive will.
REFERENCE = [
    ("cumhuriyet", FEB_2023, 4_500),
    ("euronews-tr", FEB_2023, 290),
    ("trt-haber", FEB_2023, 3_800),
    ("star", FEB_2023, 2_500),
    ("aksam", FEB_2023, 3_000),
    ("sozcu", Month(2024, 6), 2_500),
    ("a-haber", FEB_2023, 1_800),
    ("aydinlik", FEB_2023, 3_200),
    ("bloomberg-ht", FEB_2023, 490),
    ("diken", FEB_2023, 950),
    ("evrensel", FEB_2023, 1_400),
    ("haber-global", FEB_2023, 2_850),
    ("haberturk", FEB_2023, 3_550),
    ("kisa-dalga", FEB_2023, 2_000),
    ("mynet", FEB_2023, 3_100),
    ("ntv", FEB_2023, 1_900),
    ("odatv", FEB_2023, 1_700),
    ("olay", FEB_2023, 1_350),
    ("ozgur-kocaeli", FEB_2023, 1_200),
    ("sabah", FEB_2023, 6_300),
    ("sputnik-tr", FEB_2023, 1_650),
    ("takvim", FEB_2023, 1_700),
    ("timeturk", FEB_2023, 750),
    ("turkgun", FEB_2023, 1_250),
    ("yeni-asir", FEB_2023, 1_550),
]
MIN_TITLED = 0.9
"""Outlets whose files list headlines: the share of entries that must have one."""
HABERTURK_LOOKAHEAD = 150
"""Habertürk's February 2023 articles found in March's file: 304 on 2026-11-23."""


@pytest.fixture(scope="module")
def http() -> Iterator[Http]:
    client = Http()
    yield client
    client.close()


def today() -> date:
    return datetime.now(ISTANBUL).date()


def outlet_id(outlet: Outlet) -> str:
    return outlet.id


@pytest.mark.live
@pytest.mark.parametrize("outlet", builtin(include_opt_in=True), ids=outlet_id)
def test_every_outlet_passes_its_health_check(http: Http, outlet: Outlet) -> None:
    health = check(outlet, http, today=today())
    assert health.ok, "; ".join(health.problems)


@pytest.mark.live
@pytest.mark.parametrize(
    ("outlet_id", "month", "minimum"), REFERENCE, ids=[case[0] for case in REFERENCE]
)
def test_reference_months_still_hold_their_articles(
    http: Http, outlet_id: str, month: Month, minimum: int
) -> None:
    outlet = get(outlet_id)
    found = scan(outlet, http, month.start, month.next().start, today=today())
    candidates = list(found)
    assert found.gaps == []
    assert len(candidates) >= minimum, f"{len(candidates)} articles in {month}"
    if getattr(outlet, "titles", None) is not None:
        titled = sum(1 for candidate in candidates if candidate.title)
        assert titled >= MIN_TITLED * len(candidates), f"{titled} of {len(candidates)} titled"
    if outlet_id == "haberturk":
        later = month.next()
        ahead = sum(1 for c in candidates if f"{later.year}{later.month:02d}" in c.source)
        assert ahead >= HABERTURK_LOOKAHEAD, f"{ahead} articles from {later}'s file"


def test_every_built_in_outlet_has_a_reference_month() -> None:
    assert {case[0] for case in REFERENCE} == {
        outlet.id for outlet in builtin(include_opt_in=True) if outlet.id != "milliyet"
    }
