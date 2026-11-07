"""Speed budget: a year of one outlet's archive is about 100,000 candidates."""

from __future__ import annotations

import random
import time

import pytest

from tr_news_scraper.matching import KeywordQuery

WORDS = [
    "deprem",
    "kahramanmaraş",
    "heyelan",
    "çığ",
    "tsunami",
    "sel",
    "seller",
    "selam",
    "kişisel",
    "brüksel",
    "bakan",
    "açıklama",
    "yaptı",
    "meclis",
    "gündem",
    "ekonomi",
    "dolar",
    "faiz",
    "enflasyon",
    "maç",
    "gol",
    "futbol",
    "hava",
    "durumu",
    "yağmur",
    "kar",
    "uyarı",
    "afad",
    "kandilli",
    "büyüklüğünde",
    "akdeniz",
    "ege",
    "istanbul",
    "ankara",
    "izmir",
    "rize",
    "van",
]


def candidates(count: int) -> list[tuple[str, str]]:
    rng = random.Random(7)  # noqa: S311 - test data, not security
    rows = []
    for number in range(count):
        title = " ".join(rng.choice(WORDS) for _ in range(9)).capitalize()
        slug = "-".join(rng.choice(WORDS) for _ in range(6))
        rows.append((title, f"https://www.example.com/turkiye/{slug}-{number}"))
    return rows


# The budget is for the matcher as users run it. Before Python 3.14, coverage traces every line
# and slows this loop by about half, so coverage is paused for this test.
@pytest.mark.no_cover
def test_100k_candidates_and_5_keywords_take_under_5_seconds() -> None:
    query = KeywordQuery(["deprem", "sel", "heyelan", "çığ", "tsunami"])
    rows = candidates(100_000)
    started = time.perf_counter()
    hits = sum(1 for title, url in rows if query.match(title=title, url=url))
    elapsed = time.perf_counter() - started
    assert hits > 0
    assert elapsed < 5.0, f"took {elapsed:.2f} s"
