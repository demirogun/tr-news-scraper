"""Live check (weekly CI only): "deprem" in February 2023 comes from at least four outlets.

This is SPEC.md's success criterion 2. It runs after the outlet live tests, in the same session
and the same cache, so February 2023's sitemap files are usually read from the cache; the new
requests are the outlets' indexes and Milliyet's search.
"""

from __future__ import annotations

import pytest

from tr_news_scraper import search

# The built-in outlets whose archives cover February 2023.
COVERING = {"cumhuriyet", "euronews-tr", "trt-haber", "star", "aksam"}


@pytest.mark.live
def test_deprem_in_february_2023_comes_from_at_least_four_outlets() -> None:
    result = search(["deprem"], "2023-02-01", "2023-03-01")
    print(result)
    assert len(set(result.articles["outlet"]) & COVERING) >= 4, str(result)
    assert set(result.articles["month"]) == {"2023-02"}
    empty = result.report[result.report["articles"] == 0]
    assert (empty["detail"] != "").all(), str(result)
