"""Extraction (F3, F5): each outlet's page skeleton yields its headline, byline, publication time
and text, with fetch's settings: structured data first, then trafilatura."""

from __future__ import annotations

import json
import logging
import statistics
import time
from datetime import datetime
from pathlib import Path
from typing import Any

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
from tr_news_scraper._structured import alike, read_page
from tr_news_scraper.matching import KeywordQuery
from tr_news_scraper.outlets import get
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
        "Ayşe Demir",
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
        # The page's own headline; its og:title, which 1.0 gave, is worded differently.
        "Kahramanmaraş depremleri sonrası Suriye'de 22 kişi kolera nedeniyle hayatını kaybetti",
        None,
        # The page says 17:04:31+01:00; 1.0 kept only the day from its URL.
        datetime(2023, 2, 28, 19, 4, 31, tzinfo=ISTANBUL),
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
        "Hatay'da 4,1 büyüklüğünde deprem",
        "Haber Merkezi",
        datetime(2024, 6, 5, 10, 51, tzinfo=ISTANBUL),
    ),
    (
        "star",
        "Dünyanın en berrak göllerinden biriydi, deprem sonrası çamura bulandı",
        "IHA",
        datetime(2023, 2, 12, 6, 2, tzinfo=ISTANBUL),
    ),
    (
        "trt-haber",
        'Deprem felaketinden sonra "dijital ikiz teknolojisi" hızla yaygınlaşıyor',
        "Deniz Yılmaz",
        datetime(2023, 3, 2, 23, 48, tzinfo=ISTANBUL),
    ),
    (
        "a-haber",
        (
            "Doğal Afetlerden Koruyan Dua: Zilzal Suresi'nin TÜRKÇE-ARAPÇA OKUNUŞU "
            "| Deprem anında okunur mu?"
        ),
        "ahaber.com.tr Haber Merkezi",
        datetime(2025, 4, 23, 13, 31, tzinfo=ISTANBUL),
    ),
    (
        "aydinlik",
        (
            '"Hoşgörü Kenti"nde ezan ve çan sesinin birbirine karıştığı yapılar '
            "depremden zarar gördü"
        ),
        None,
        datetime(2023, 2, 17, 0, 34, tzinfo=ISTANBUL),
    ),
    (
        "bloomberg-ht",
        "Afet bölgesinde Deprem Suçları Soruşturma Büroları kurulacak",
        "Bloomberght",
        datetime(2023, 2, 11, 13, 50, 32, tzinfo=ISTANBUL),
    ),
]
# The pages whose lead only structured data brings back.
LEAD_FIRST = {"aksam", "cumhuriyet", "euronews-tr", "milliyet", "sozcu", "star", "trt-haber"}
PARAGRAPHS = [
    "Kahramanmaraş merkezli depremlerin ardından bölgede arama ve kurtarma çalışmaları "
    "sürüyor, ekipler gece boyunca enkaz altındaki vatandaşlara ulaşmaya çalıştı.",
    "Afet ve Acil Durum Yönetimi Başkanlığı, bölgeye gönderilen personel sayısının yüzlerce "
    "kişiyi bulduğunu ve yardım malzemelerinin dağıtımının devam ettiğini açıkladı.",
    "Yetkililer, hasar tespit çalışmalarının tamamlanmasının ardından vatandaşların güvenli "
    "binalara dönebileceğini, o zamana kadar çadır kentlerde kalmalarını istedi.",
    "Bölgedeki okulların bir süre kapalı kalacağı, öğrencilerin uzaktan eğitimle derslerine "
    "devam edeceği ve sınav takviminin yeniden düzenleneceği bildirildi.",
]
HEADLINE = "Deprem bölgesinde çalışmalar sürüyor"


def page(outlet: str) -> str:
    return (FIXTURES / outlet / "page.html").read_text(encoding="utf-8")


def synthetic(
    *,
    article: dict[str, Any] | None = None,
    head: str = "",
    header: str = f"<h1>{HEADLINE}</h1>",
    paragraphs: list[str] = PARAGRAPHS,
) -> str:
    """A small article page: optional JSON-LD and extra head tags, a header above the article
    (its <h1> by default), and the article's paragraphs."""
    data = None if article is None else json.dumps(article, ensure_ascii=False)
    script = "" if data is None else f'<script type="application/ld+json">{data}</script>'
    body = "".join(f"<p>{text}</p>" for text in paragraphs)
    return (
        f"<html><head><title>{HEADLINE} - Örnek</title>{head}{script}</head>"
        f"<body><header>{header}</header><article>{body}</article></body></html>"
    )


def news(**fields: Any) -> dict[str, Any]:
    return {"@context": "https://schema.org", "@type": "NewsArticle", **fields}


@pytest.mark.parametrize(
    ("outlet", "headline", "byline", "published"), EXPECTED, ids=[case[0] for case in EXPECTED]
)
def test_each_outlets_page_yields_headline_byline_time_and_text(
    outlet: str, headline: str, byline: str | None, published: datetime
) -> None:
    found = extract(page(outlet), f"https://www.example.com.tr/{outlet}", get(outlet).name)
    assert (found.title, found.author, found.error) == (headline, byline, None)
    assert found.published == published
    assert found.published is not None
    assert found.published.tzinfo is ISTANBUL
    assert found.text is not None
    # Where the page shows its lead, the text has it: first when trafilatura alone left it out,
    # as on every 1.0 outlet's page.
    lead = read_page(page(outlet)).lead
    if outlet in LEAD_FIRST:
        assert lead is not None
        assert found.text.startswith(f"{lead}\n")
    elif lead is not None:
        assert lead in found.text or any(alike(lead, line) for line in found.text.split("\n"))
    words = found.text.lower().split()
    filler = [word.strip(".") for word in words if word.strip(".") in FILLER]
    assert len(words) >= 30
    assert len(filler) >= 0.8 * len(words)
    assert KeywordQuery(["deprem"]).matches(text=found.text)


@pytest.mark.parametrize(
    ("stated", "url", "expected"),
    [
        ("2023-02-06T23:30:00+03:00", "https://x.com.tr/gundem/haber-1", (2, 6, 23, 30)),
        # Another offset near midnight: really 01:30 the next day in Türkiye (1.0 said 23:30).
        ("2023-02-06T23:30:00+01:00", "https://x.com.tr/gundem/haber-1", (2, 7, 1, 30)),
        # The same with a date in the URL, from which 1.0 kept only the day (02-06).
        ("2023-02-06T23:30:00+01:00", "https://x.com.tr/2023/02/06/haber", (2, 7, 1, 30)),
    ],
    ids=["istanbul", "other-offset", "date-in-url"],
)
@pytest.mark.parametrize("source", ["json-ld", "meta-tag"])
def test_a_publication_time_keeps_the_pages_offset(
    stated: str, url: str, expected: tuple[int, int, int, int], source: str
) -> None:
    if source == "json-ld":
        html = synthetic(article=news(headline=HEADLINE, datePublished=stated))
    else:
        html = synthetic(head=f'<meta property="article:published_time" content="{stated}">')
    found = extract(html, url, "Örnek")
    month, day, hour, minute = expected
    assert found.published == datetime(2023, month, day, hour, minute, tzinfo=ISTANBUL)
    assert found.published is not None
    assert found.published.tzinfo is ISTANBUL


def test_the_date_of_the_last_edit_is_never_the_publication_time() -> None:
    article = news(datePublished="2023-02-06T10:00:00+03:00", dateModified="2023-03-01T10:00:00Z")
    found = extract(synthetic(article=article), "https://x.com.tr/a", "Örnek")
    assert found.published == datetime(2023, 2, 6, 10, 0, tzinfo=ISTANBUL)


LEAD = "Deprem bölgesinde yaraları sarma çalışmaları on binlerce gönüllünün katılımıyla sürüyor."


def test_json_ld_gives_the_headline_lead_and_byline() -> None:
    article = news(
        headline=HEADLINE,
        description=LEAD,
        datePublished="2023-02-06T10:00:00+03:00",
        author=[{"@type": "Person", "name": "Ayşe Demir"}, {"@type": "Organization", "name": "AA"}],
        publisher={"@type": "Organization", "name": "Örnek"},
    )
    html = synthetic(
        article=article,
        head=f'<meta property="og:title" content="{HEADLINE} | Örnek">',
        header=f"<h1>{HEADLINE}</h1><h2>{LEAD}</h2>",
    )
    found = extract(html, "https://x.com.tr/a", "Örnek")
    assert (found.title, found.author) == (HEADLINE, "Ayşe Demir, AA")
    assert found.text is not None
    assert found.text.split("\n") == [LEAD, *PARAGRAPHS]


def test_a_lead_already_in_the_text_isnt_added_twice() -> None:
    article = news(headline=HEADLINE, description=LEAD)
    html = synthetic(article=article, header="", paragraphs=[HEADLINE, LEAD, *PARAGRAPHS])
    found = extract(html, "https://x.com.tr/a", "Örnek")
    assert found.text is not None
    assert found.text.count(LEAD) == 1


def test_a_page_without_json_ld_keeps_trafilaturas_title_and_byline() -> None:
    from trafilatura import bare_extraction

    html = synthetic(
        header="",
        head=(
            '<meta property="og:title" content="Başlık | Örnek">'
            '<meta name="author" content="Ayşe Demir">'
        ),
    )
    found = extract(html, "https://x.com.tr/a", "Örnek")
    plain: Any = bare_extraction(html, with_metadata=True)
    assert (found.title, found.author) == (plain.title, plain.author)
    assert found.text is not None
    assert found.text.split("\n") == PARAGRAPHS


def test_when_no_text_is_found_the_pages_own_facts_still_count() -> None:
    article = news(headline=HEADLINE, datePublished="2023-02-06T10:00:00+03:00")
    found = extract(
        synthetic(article=article, header="", paragraphs=[]), "https://x.com.tr/a", "Örnek"
    )
    assert found == Extracted(
        title=HEADLINE,
        published=datetime(2023, 2, 6, 10, 0, tzinfo=ISTANBUL),
        error="no article text found",
    )


def test_text_keeps_paragraph_breaks_but_no_blank_lines_or_runs_of_spaces() -> None:
    found = extract(page("trt-haber"), "https://www.trthaber.com/haber/a-1.html", "TRT Haber")
    assert found.text is not None
    lines = found.text.split("\n")
    assert len(lines) > 5
    assert all(line == line.strip() and line for line in lines)
    assert "  " not in found.text


def test_a_page_without_article_text_is_an_error() -> None:
    found = extract(
        "<html><head><title>Boş</title></head><body></body></html>", "https://x.com.tr/a"
    )
    assert found.error == "no article text found"
    assert found.text is None


def test_a_page_too_large_to_read_is_an_error_without_parsing_it() -> None:
    huge = "<html><body>" + "a" * (MAX_PAGE_CHARACTERS + 1) + "</body></html>"
    found = extract(huge, "https://x.com.tr/a")
    assert found == Extracted(error="the page is too large to read (8.0 million characters)")


def test_nothing_a_page_says_reaches_the_librarys_logs(caplog: pytest.LogCaptureFixture) -> None:
    article = news(headline="Gizli başlık", description="Gizli özet", author={"name": "Gizli Ad"})
    with caplog.at_level(logging.DEBUG, logger="tr_news_scraper"):
        extract(synthetic(article=article), "https://x.com.tr/a", "Örnek")
    ours = [r for r in caplog.records if r.name.startswith("tr_news_scraper")]
    assert not any("Gizli" in r.getMessage() for r in ours)


def test_a_record_round_trips_through_json() -> None:
    fetched_at = datetime(2026, 11, 8, 10, 0, tzinfo=ISTANBUL)
    found = extract(page("star"), "https://www.star.com.tr/a", "Star")
    assert from_json(to_json(found, fetched_at)) == (found, fetched_at)
    undated = Extracted(title="Başlık", text="Metin")
    assert from_json(to_json(undated, fetched_at)) == (undated, fetched_at)


def test_the_extractor_version_names_trafilatura_and_the_settings() -> None:
    assert extractor().startswith("trafilatura 2.")
    assert "structured data first" in extractor()
    assert "precision" in extractor()


def test_trafilatura_is_imported_only_inside_the_extraction() -> None:
    assert "trafilatura" not in vars(extract_module)
    assert "bare_extraction" not in vars(extract_module)


# Like the other speed budgets, this runs with coverage paused.
@pytest.mark.no_cover
def test_extraction_takes_under_100_ms_per_page_at_the_median() -> None:
    pages = [(page(case[0]), get(case[0]).name) for case in EXPECTED]
    warm_up, name = pages[0]
    extract(warm_up, "https://x.com.tr/warm-up", name)
    times = []
    for html, name in pages * 3:
        started = time.perf_counter()
        extract(html, "https://x.com.tr/a", name)
        times.append(time.perf_counter() - started)
    assert statistics.median(times) < 0.1, f"median {statistics.median(times) * 1000:.0f} ms"


def test_a_document_with_metadata_but_no_text_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class Document:
        title = "Başlık"
        author = None
        date = "2023-02-12"
        text = "  \n "

    monkeypatch.setattr("trafilatura.bare_extraction", lambda *args, **kwargs: Document())
    found = extract("<html><body><p>x</p></body></html>", "https://x.com.tr/a")
    assert found == Extracted(
        title="Başlık",
        published=datetime(2023, 2, 12, tzinfo=ISTANBUL),
        error="no article text found",
    )


def test_trafilaturas_date_is_asked_for_with_its_offset(monkeypatch: pytest.MonkeyPatch) -> None:
    asked: dict[str, Any] = {}

    class Document:
        title = author = None
        date = "2023-02-06T23:30:00+0100"
        text = "Metin."

    def bare_extraction(*args: Any, **kwargs: Any) -> Document:
        asked.update(kwargs["date_extraction_params"])
        return Document()

    monkeypatch.setattr("trafilatura.bare_extraction", bare_extraction)
    found = extract("<html><body><p>x</p></body></html>", "https://x.com.tr/2023/02/06/a")
    assert found.published == datetime(2023, 2, 7, 1, 30, tzinfo=ISTANBUL)
    assert asked["outputformat"].endswith("%z")
    assert asked["deferred_url_extractor"] is True
    assert (asked["original_date"], asked["extensive_search"]) == (True, False)


def test_helpers_tidy_paragraphs() -> None:
    assert extract_module._paragraphs(None) is None
    assert extract_module._paragraphs(" \n\n ") is None
    assert extract_module._paragraphs(" Bir  iki \n\n üç ") == "Bir iki\nüç"
