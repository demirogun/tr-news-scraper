"""Live check (weekly CI only): "deprem" in February 2023 comes from at least 18 outlets.

This is SPEC.md's success criterion 2, as 1.1 raised it. It runs after the outlet live tests, in
the same session and the same cache, so February 2023's sitemap files are usually read from the
cache; the new requests are the outlets' indexes and Milliyet's search.
"""

from __future__ import annotations

import pytest

from tr_news_scraper import search
from tr_news_scraper.outlets import builtin

# The default outlets whose archives cover February 2023: all but Sözcü (from December 2023) and
# Milliyet, whose search reaches back about two and a half years.
COVERING = {outlet.id for outlet in builtin()} - {"sozcu", "milliyet"}
MIN_OUTLETS = 18


def test_twenty_three_default_outlets_cover_february_2023() -> None:
    assert len(COVERING) == 23


@pytest.mark.live
def test_deprem_in_february_2023_comes_from_at_least_eighteen_outlets() -> None:
    result = search(["deprem"], "2023-02-01", "2023-03-01")
    print(result)
    assert len(set(result.articles["outlet"]) & COVERING) >= MIN_OUTLETS, str(result)
    assert set(result.articles["month"]) == {"2023-02"}
    empty = result.report[result.report["articles"] == 0]
    assert (empty["detail"] != "").all(), str(result)
