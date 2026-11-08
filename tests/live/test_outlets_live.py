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

# About half of what each reference month held on 2026-11-07: deleting some articles won't trip
# the check, a broken archive will.
REFERENCE = [
    ("cumhuriyet", Month(2023, 2), 4_500),
    ("euronews-tr", Month(2023, 2), 290),
    ("trt-haber", Month(2023, 2), 3_800),
    ("star", Month(2023, 2), 2_500),
    ("aksam", Month(2023, 2), 3_000),
    ("sozcu", Month(2024, 6), 2_500),
]


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
@pytest.mark.parametrize("outlet", builtin(), ids=outlet_id)
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
    found = scan(get(outlet_id), http, month.start, month.next().start, today=today())
    candidates = list(found)
    assert found.gaps == []
    assert len(candidates) >= minimum, f"{len(candidates)} articles in {month}"
    if outlet_id == "star":
        titled = sum(1 for candidate in candidates if candidate.title)
        assert titled >= 0.9 * len(candidates), f"{titled} of {len(candidates)} have headlines"
