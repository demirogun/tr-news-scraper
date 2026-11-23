"""The page skeletons hold no article text, and the script that makes them follows its rules."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import lxml.html
import pytest

from tr_news_scraper.matching import fold, tr_lower

FIXTURES = Path(__file__).parent / "fixtures"
OUTLETS = (
    "a-haber",
    "aksam",
    "aydinlik",
    "bloomberg-ht",
    "cumhuriyet",
    "diken",
    "euronews-tr",
    "evrensel",
    "haber-global",
    "haberturk",
    "kisa-dalga",
    "milliyet",
    "mynet",
    "ntv",
    "odatv",
    "olay",
    "sozcu",
    "star",
    "trt-haber",
)
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
    long = first.filler(9)
    assert long == second.filler(9)
    assert len(long.split()) == 9
    assert long.endswith(".")
    assert set(words(long)) <= ALLOWED
    assert words(long)[1] == "deprem"
    assert "deprem" not in words(first.filler(7))


def test_fillers_of_different_texts_differ() -> None:
    skeleton = script.Skeleton({})
    fillers = [skeleton.filler(12) for _ in range(50)]
    assert len(set(fillers)) == 50


def test_filler_capitalizes_the_turkish_way() -> None:
    assert script.capitalized("içerik bölüm") == "İçerik bölüm"
    assert script.capitalized("ırmak") == "Irmak"
    assert script.capitalized("örnek") == "Örnek"


def test_short_texts_dates_and_times_are_kept() -> None:
    skeleton = script.Skeleton({})
    assert skeleton.replace_long("Haber Merkezi") == "Haber Merkezi"
    assert skeleton.replace_long("02.03.2023 23:48") == "02.03.2023 23:48"
    replaced = skeleton.replace_long("Bu üç kelime")
    assert replaced is not None
    assert len(replaced.split()) == 3
    assert set(words(replaced)) <= ALLOWED
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
    body = re.match(r'\{"articleBody": "([^"]*)", "headline": "Başlık",\}$', edited)
    assert body is not None
    assert len(body.group(1).split()) == 4
    assert set(words(body.group(1))) <= ALLOWED


def test_an_author_needs_a_fictional_name() -> None:
    assert script.parse_authors(["Ali Veli=Ayşe Demir"]) == {"Ali Veli": "Ayşe Demir"}
    with pytest.raises(SystemExit, match="Real Name=Fictional Name"):
        script.parse_authors(["Ali Veli"])


LEAD = "Bölgedeki okullarda eğitim yeniden başladı ve öğrenciler sınıflarına döndü."


def lead_page(author: object = None, meta_author: str | None = None) -> str:
    article: dict[str, object] = {"@type": "NewsArticle", "headline": "Başlık", "description": LEAD}
    if author is not None:
        article["author"] = author
    meta = "" if meta_author is None else f'<meta name="author" content="{meta_author}">'
    return f"""<html><head><title>Başlık</title>
    <meta name="description" content="{LEAD}"><meta property="og:description" content="{LEAD}">
    {meta}<script type="application/ld+json">{json.dumps(article, ensure_ascii=False)}</script>
    </head><body><h1>Başlık</h1><h2>  {LEAD}  </h2>
    <div class="author-box">Muhabir Kişi</div><p>Metnin ilk paragrafı burada yazıyor.</p>
    <p>Muhabir Kişi bildiriyor.</p></body></html>"""


def built(page: str, authors: dict[str, str] | None = None) -> tuple[str, Any]:
    skeleton = script.Skeleton(authors or {}).build(page)
    return skeleton, lxml.html.document_fromstring(skeleton)


def json_ld(root: Any) -> Any:
    return json.loads(root.xpath("//script[@type='application/ld+json']")[0].text)


def test_equal_texts_get_equal_filler_wherever_they_are() -> None:
    _, root = built(lead_page())
    fillers = {
        json_ld(root)["description"],
        root.xpath("string(//meta[@name='description']/@content)"),
        root.xpath("string(//meta[@property='og:description']/@content)"),
        " ".join(root.xpath("string(//h2)").split()),
    }
    assert len(fillers) == 1
    assert set(words(fillers.pop())) <= ALLOWED


def test_different_texts_still_get_different_filler() -> None:
    _, root = built(lead_page())
    paragraphs = [p.text_content() for p in root.iter("p")]
    assert len(set(paragraphs)) == 2


@pytest.mark.parametrize(
    "author",
    [
        {"@type": "Person", "name": "Muhabir Kişi"},
        [{"@type": "Person", "name": "Muhabir Kişi"}],
        "Muhabir Kişi",
        {"@type": "Person", "name": "MUHABİR KİŞİ / muhabir@ornek.com.tr"},
    ],
    ids=["object", "list", "string", "capitals-and-email"],
)
def test_a_json_ld_byline_becomes_fictional_everywhere_without_an_author_option(
    author: object,
) -> None:
    skeleton, root = built(lead_page(author=author))
    for spelling in ("Muhabir Kişi", "MUHABİR KİŞİ", "muhabir-kisi"):
        assert spelling not in skeleton
    stated = json_ld(root)["author"]
    name = stated[0] if isinstance(stated, list) else stated
    name = name["name"] if isinstance(name, dict) else name
    fictional = tr_lower(name.split(" / ")[0])
    assert fictional in {tr_lower(name) for name in script.FICTIONAL_NAMES}
    assert tr_lower(root.xpath("string(//div[@class='author-box'])").strip()) == fictional


def test_a_meta_author_becomes_fictional_too() -> None:
    skeleton, root = built(lead_page(meta_author="Muhabir Kişi"))
    assert "Muhabir Kişi" not in skeleton
    assert root.xpath("string(//meta[@name='author']/@content)") in script.FICTIONAL_NAMES


@pytest.mark.parametrize(
    "author",
    [
        {"@type": "Person", "name": "IHA"},
        {"@type": "Person", "name": "Haber Merkezi"},
        {"@type": "Organization", "name": "Örnek Medya Grubu"},
        {"@type": "NewsMediaOrganization", "name": "Örnek Medya Grubu"},
        {"@type": "Person", "name": "Anadolu Ajansı"},
    ],
)
def test_desks_agencies_and_organizations_keep_their_names(author: dict[str, str]) -> None:
    _, root = built(lead_page(author=author))
    assert json_ld(root)["author"]["name"] == author["name"]


def test_an_author_option_still_decides_the_fictional_name() -> None:
    skeleton, root = built(
        lead_page(author={"@type": "Person", "name": "Muhabir Kişi"}),
        {"Muhabir Kişi": "Elif Kaya"},
    )
    assert json_ld(root)["author"]["name"] == "Elif Kaya"
    assert "Muhabir Kişi" not in skeleton


def test_each_real_name_gets_its_own_fictional_name() -> None:
    authors = [
        {"@type": "Person", "name": "Muhabir Kişi"},
        {"@type": "Person", "name": "Öteki Yazar"},
    ]
    _, root = built(lead_page(author=authors))
    first, second = (entry["name"] for entry in json_ld(root)["author"])
    assert first != second
    assert {first, second} <= set(script.FICTIONAL_NAMES)


def test_a_byline_is_replaced_in_lowercase_folded_and_as_a_username_too() -> None:
    extra = (
        '<meta name="keywords" content="deprem,muhabir kişi,muhabir kisi">'
        '<meta property="creators" content="mkisi">'
        '<meta name="twitter:creator" content="@muhabir.kisi">'
        '<link rel="canonical" href="https://www.ornek.com.tr/yazar/muhabir_kisi">'
    )
    page = lead_page(author={"@type": "Person", "name": "Muhabir Kişi"}).replace(
        "<title>Başlık</title>", f"<title>Başlık</title>{extra}"
    )
    skeleton, _ = built(page)
    assert "kisi" not in fold(skeleton)
    assert "muhabir" not in fold(skeleton)


@pytest.mark.parametrize("name", ["Cumartesi Com Tr", "Dış Haberler Servisi", "AA", "Reuters"])
def test_addresses_desks_and_agencies_are_not_people(name: str) -> None:
    assert script._is_desk(name)


def test_a_surname_that_starts_like_a_desk_word_is_still_a_person() -> None:
    assert not script._is_desk("Mehmet Haberal")


def test_texts_98_percent_alike_get_equal_filler_too() -> None:
    skeleton = script.Skeleton({})
    shown = skeleton.replace_long(LEAD)
    assert skeleton.replace_long(LEAD.replace("yeniden", "yeni den")) == shown
    assert skeleton.replace_long("Bambaşka bir cümle burada duruyor ve hiç benzemiyor.") != shown


def test_an_author_profile_url_loses_its_username() -> None:
    # Diken's and Olay's JSON-LD point at profile pages whose username is one word of the name.
    article = {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "NewsArticle", "author": {"@id": "https://x.com.tr/author/kisi/#author"}},
            {
                "@type": "Person",
                "@id": "https://x.com.tr/author/kisi/#author",
                "name": "Muhabir Kişi",
            },
        ],
    }
    page = (
        f'<html><head><script type="application/ld+json">{json.dumps(article, ensure_ascii=False)}'
        '</script></head><body><a href="https://x.com.tr/yazar/mkisi99">Yazar</a></body></html>'
    )
    skeleton = script.Skeleton({"Muhabir Kişi": "Elif Kaya"}).build(page)
    assert "kisi" not in fold(skeleton)
    assert skeleton.count("/author/elif-kaya/") == 2
    assert "/yazar/elif-kaya" in skeleton


def test_other_journalists_named_in_author_elements_become_fictional_too() -> None:
    # Milliyet's sidebar lists other columnists in elements named like the page's own byline.
    page = """<html><body><p class="byline">Muhabir Kişi</p>
    <div class="columnist-list"><a class="author-name" href="/yazarlar/oteki">Öteki Yazar Adı</a>
    <span class="writer">Haber Merkezi</span><span class="author-label">Yazarlar</span></div>
    <p>Metnin ilk paragrafı burada yazıyor.</p></body></html>"""
    skeleton = script.Skeleton({}).build(page)
    built = lxml.html.document_fromstring(skeleton)
    assert "Öteki" not in skeleton
    assert "Muhabir" not in skeleton
    assert built.xpath("string(//a[@class='author-name'])") in script.FICTIONAL_NAMES
    assert built.xpath("string(//span[@class='writer'])") == "Haber Merkezi"
    assert built.xpath("string(//span[@class='author-label'])") == "Yazarlar"


def test_a_link_to_an_authors_page_loses_the_authors_name() -> None:
    page = """<html><body><nav><a href="/yazar/oteki-yazar">Öteki Yazar</a></nav>
    <p>Metnin ilk paragrafı burada yazıyor.</p></body></html>"""
    skeleton = script.Skeleton({}).build(page)
    assert "Öteki" not in skeleton
    built = lxml.html.document_fromstring(skeleton)
    assert built.xpath("string(//nav/a)") in script.FICTIONAL_NAMES


@pytest.mark.parametrize(
    ("text", "name"),
    [
        ("Ayşe Demir", True),
        ("AYŞE DEMİR", True),
        ("Ahmet Hakan Yılmaz", True),
        ("Yayınlanma: 28 Şubat 2023 - 22:34", False),
        ("Hayat yenilenir mi bu kış", False),
        ("Yazarlar", False),
    ],
)
def test_only_name_like_texts_count_as_names(text: str, name: bool) -> None:
    assert script.looks_like_name(text) is name


def test_a_date_line_in_an_author_element_keeps_its_text() -> None:
    page = """<html><body><div class="author-article-date"><time>Yayınlanma: 28 Şubat 2023 - 22:34
    </time></div><p>Metnin ilk paragrafı burada yazıyor.</p></body></html>"""
    skeleton = script.Skeleton({}).build(page)
    assert "Yayınlanma: 28 Şubat 2023 - 22:34" in skeleton
