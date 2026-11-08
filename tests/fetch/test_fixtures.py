"""The page skeletons hold no article text, and the script that makes them follows its rules."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from types import ModuleType

import lxml.html
import pytest

from tr_news_scraper.matching import tr_lower

FIXTURES = Path(__file__).parent / "fixtures"
OUTLETS = ("aksam", "cumhuriyet", "euronews-tr", "milliyet", "sozcu", "star", "trt-haber")
LETTERS = re.compile(r"[^\W\d_]+")


def load_script() -> ModuleType:
    path = Path(__file__).parents[2] / "scripts" / "make_page_fixtures.py"
    spec = importlib.util.spec_from_file_location("make_page_fixtures", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


script = load_script()
ALLOWED = frozenset(script.FILLER) | {script.KEYWORD}


def words(text: str) -> list[str]:
    return [tr_lower(word) for word in LETTERS.findall(text)]


@pytest.mark.parametrize("outlet", OUTLETS)
def test_every_paragraph_in_a_skeleton_is_filler(outlet: str) -> None:
    page = lxml.html.parse(str(FIXTURES / outlet / "page.html")).getroot()
    paragraphs = [p.text_content() for p in page.iter("p")]
    long = [text for text in paragraphs if len(words(text)) >= script.MIN_WORDS]
    assert long, "the skeleton should keep its paragraphs"
    leftovers = [text[:60] for text in long if not set(words(text)) <= ALLOWED]
    assert leftovers == []


@pytest.mark.parametrize("outlet", OUTLETS)
def test_every_json_ld_body_and_description_is_filler(outlet: str) -> None:
    page = lxml.html.parse(str(FIXTURES / outlet / "page.html")).getroot()
    for block in page.xpath("//script[@type='application/ld+json']"):
        found = re.findall(r'"(?:articleBody|description)"\s*:\s*"([^"]*)"', block.text or "")
        for text in found:
            assert set(words(text)) <= ALLOWED, text[:60]


@pytest.mark.parametrize("outlet", OUTLETS)
def test_a_skeleton_keeps_its_headline_and_declares_utf8(outlet: str) -> None:
    html = (FIXTURES / outlet / "page.html").read_text(encoding="utf-8")
    page = lxml.html.document_fromstring(html)
    assert page.findtext(".//title")
    assert page.xpath("//meta[@charset='utf-8']")
    assert not page.xpath("//script[not(@type='application/ld+json')] | //style | //iframe")


def test_filler_is_deterministic_and_names_deprem_in_long_texts() -> None:
    first, second = script.Skeleton({}), script.Skeleton({})
    assert first.filler(9) == second.filler(9)
    assert script.Skeleton({}).filler(9) == (
        "Örnek deprem yer tutucu cümle paragraf sayfa satır kelime."
    )
    assert first.filler(3) == "Deneme içerik bölüm."


def test_filler_capitalizes_the_turkish_way() -> None:
    skeleton = script.Skeleton({})
    skeleton.seed = script.FILLER.index("içerik")
    assert skeleton.filler(3) == "İçerik bölüm örnek."


def test_short_texts_dates_and_times_are_kept() -> None:
    skeleton = script.Skeleton({})
    assert skeleton.replace_long("Haber Merkezi") == "Haber Merkezi"
    assert skeleton.replace_long("02.03.2023 23:48") == "02.03.2023 23:48"
    assert skeleton.replace_long("Bu üç kelime") == "Örnek metin yer."
    assert skeleton.replace_long(None) is None


def test_a_page_keeps_its_structure_but_not_its_words() -> None:
    page = """<html><head><meta charset="windows-1254"><title>Başlık burada</title>
    <meta name="description" content="Bu haberin özeti burada yazıyor">
    <link rel="stylesheet" href="a.css"><link rel="canonical" href="https://x.com.tr/a">
    <script>var tracking = "Gizli izleme kodu burada";</script></head>
    <body><h1>Gerçek başlık üç kelimeden uzun</h1>
    <div class="article-date">12 Şubat 2023 Pazar 06:02</div>
    <p>Gerçek haber metni burada yazıyor ve telif hakkıyla korunuyor.</p>
    <p class="byline">Ali Veli</p><!-- a comment -->
    <img alt="Fotoğrafın uzun bir açıklaması burada" src="a.jpg">
    <script type="application/ld+json">{"articleBody": "Gerçek metin burada da var",
     "author": {"name": "Ali Veli"}}</script></body></html>"""
    skeleton = script.Skeleton({"Ali Veli": "Ayşe Demir"}).build(page)
    built = lxml.html.document_fromstring(skeleton)
    assert built.findtext(".//h1") == "Gerçek başlık üç kelimeden uzun"
    assert built.xpath("string(//div[@class='article-date'])") == "12 Şubat 2023 Pazar 06:02"
    assert set(words(built.xpath("string(//p[1])"))) <= ALLOWED
    assert built.xpath("string(//p[@class='byline'])") == "Ayşe Demir"
    assert set(words(built.xpath("string(//img/@alt)"))) <= ALLOWED
    assert built.xpath("//meta[@charset]/@charset") == ["utf-8"]
    assert built.xpath("//link/@rel") == ["canonical"]
    assert "Gizli" not in skeleton
    assert "a comment" not in skeleton
    data = json.loads(built.xpath("//script[@type='application/ld+json']")[0].text)
    assert data["author"]["name"] == "Ayşe Demir"
    assert set(words(data["articleBody"])) <= ALLOWED


def test_malformed_json_ld_is_edited_in_place_not_dropped() -> None:
    skeleton = script.Skeleton({})
    malformed = '{"articleBody": "Gerçek metin burada var", "headline": "Başlık",}'
    edited = skeleton._json_ld_text(malformed)
    assert edited.startswith('{"articleBody": "Örnek metin yer tutucu."')
    assert edited.endswith('"headline": "Başlık",}')


def test_an_author_needs_a_fictional_name() -> None:
    assert script.parse_authors(["Ali Veli=Ayşe Demir"]) == {"Ali Veli": "Ayşe Demir"}
    with pytest.raises(SystemExit, match="Real Name=Fictional Name"):
        script.parse_authors(["Ali Veli"])
