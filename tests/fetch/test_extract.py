"""Extraction (F3, F5): each outlet's page skeleton yields its headline, byline, publication time
and text, with fetch's trafilatura settings."""

from __future__ import annotations

import statistics
import time
from datetime import datetime
from pathlib import Path

import pytest

import tr_news_scraper._extract as extract_module
from tr_news_scraper._extract import (
    MAX_PAGE_CHARACTERS,
    Extracted,
    extract,
    extractor,
    from_json,
    to_json,
)
from tr_news_scraper.matching import KeywordQuery
from tr_news_scraper.outlets._dates import ISTANBUL

FIXTURES = Path(__file__).parent / "fixtures"
FILLER = {
    "örnek",
    "metin",
    "yer",
    "tutucu",
    "cümle",
    "paragraf",
    "sayfa",
    "satır",
    "kelime",
    "deneme",
    "içerik",
    "bölüm",
    "deprem",
}
# outlet, headline, byline, publication time in Türkiye
EXPECTED = [
    (
        "aksam",
        "Çocuklara deprem nasıl anlatılır?",
        "AYŞE DEMİR; Cumartesi Com Tr",
        datetime(2023, 2, 25, 7, 0, tzinfo=ISTANBUL),
    ),
    (
        "cumhuriyet",
        "ABD'li uzay şirketi depremin uydu görüntülerini yayımladı",
        "Haber Merkezi",
        datetime(2023, 2, 8, 12, 27, tzinfo=ISTANBUL),
    ),
    (
        "euronews-tr",
        "Kahramanmaraş depremleri sonrası Suriye'de 22 kişi koleradan öldü",
        None,
        datetime(2023, 2, 28, 0, 0, tzinfo=ISTANBUL),
    ),
    (
        "milliyet",
        "SON DEPREMLER LİSTESİ 7 KASIM! Az önce deprem mi oldu, nerede, kaç şiddetinde? "
        "AFAD/Kandilli deprem sorgulama",
        "Elif Kaya",
        datetime(2026, 11, 7, 7, 25, 23, tzinfo=ISTANBUL),
    ),
    (
        "sozcu",
        "Hatay'da 4,1 büyüklüğünde deprem - Sözcü Gazetesi",
        "Haber Merkezi",
        datetime(2024, 6, 5, 10, 51, tzinfo=ISTANBUL),
    ),
    (
        "star",
        "Dünyanın en berrak göllerinden biriydi, deprem sonrası çamura bulandı | STAR",
        "IHA",
        datetime(2023, 2, 12, 6, 2, tzinfo=ISTANBUL),
    ),
    (
        "trt-haber",
        'Deprem felaketinden sonra "dijital ikiz teknolojisi" hızla yaygınlaşıyor',
        "Deniz Yılmaz",
        datetime(2023, 3, 2, 23, 48, tzinfo=ISTANBUL),
    ),
]


def page(outlet: str) -> str:
    return (FIXTURES / outlet / "page.html").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("outlet", "headline", "byline", "published"), EXPECTED, ids=[case[0] for case in EXPECTED]
)
def test_each_outlets_page_yields_headline_byline_time_and_text(
    outlet: str, headline: str, byline: str | None, published: datetime
) -> None:
    found = extract(page(outlet), f"https://www.example.com.tr/{outlet}")
    assert (found.title, found.author, found.error) == (headline, byline, None)
    assert found.published == published
    assert found.published is not None
    assert found.published.tzinfo is ISTANBUL
    assert found.text is not None
    words = found.text.lower().split()
    filler = [word.strip(".") for word in words if word.strip(".") in FILLER]
    assert len(words) >= 30
    assert len(filler) >= 0.8 * len(words)
    assert KeywordQuery(["deprem"]).matches(text=found.text)


def test_text_keeps_paragraph_breaks_but_no_blank_lines_or_runs_of_spaces() -> None:
    found = extract(page("trt-haber"), "https://www.trthaber.com/haber/a-1.html")
    assert found.text is not None
    lines = found.text.split("\n")
    assert len(lines) > 5
    assert all(line == line.strip() and line for line in lines)
    assert "  " not in found.text


def test_a_page_without_article_text_is_an_error() -> None:
    found = extract("<html><head><title>Boş</title></head><body></body></html>", "https://x.com.tr/a")
    assert found.error == "no article text found"
    assert found.text is None


def test_a_page_too_large_to_read_is_an_error_without_parsing_it() -> None:
    huge = "<html><body>" + "a" * (MAX_PAGE_CHARACTERS + 1) + "</body></html>"
    found = extract(huge, "https://x.com.tr/a")
    assert found == Extracted(error="the page is too large to read (8.0 million characters)")


def test_a_record_round_trips_through_json() -> None:
    fetched_at = datetime(2026, 11, 8, 10, 0, tzinfo=ISTANBUL)
    found = extract(page("star"), "https://www.star.com.tr/a")
    assert from_json(to_json(found, fetched_at)) == (found, fetched_at)
    undated = Extracted(title="Başlık", text="Metin")
    assert from_json(to_json(undated, fetched_at)) == (undated, fetched_at)


def test_the_extractor_version_names_trafilatura_and_the_settings() -> None:
    assert extractor().startswith("trafilatura 2.")
    assert "precision" in extractor()


def test_trafilatura_is_imported_only_inside_the_extraction() -> None:
    assert "trafilatura" not in vars(extract_module)
    assert "bare_extraction" not in vars(extract_module)


# Like the other speed budgets, this runs with coverage paused.
@pytest.mark.no_cover
def test_extraction_takes_under_100_ms_per_page_at_the_median() -> None:
    pages = [page(case[0]) for case in EXPECTED]
    extract(pages[0], "https://x.com.tr/warm-up")
    times = []
    for html in pages * 3:
        started = time.perf_counter()
        extract(html, "https://x.com.tr/a")
        times.append(time.perf_counter() - started)
    assert statistics.median(times) < 0.1, f"median {statistics.median(times) * 1000:.0f} ms"
