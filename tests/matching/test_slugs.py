"""URL slugs: which part of a URL counts, and matching it in folded (ASCII) form."""

from __future__ import annotations

import pytest

from tr_news_scraper.matching import KeywordQuery, url_slug_tokens


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (  # Cumhuriyet: category folder, slug, numeric id
            "https://www.cumhuriyet.com.tr/turkiye/kahramanmarasta-deprem-2045001",
            ["kahramanmarasta", "deprem"],
        ),
        (  # Euronews Türkçe: date folders, slug without id
            "https://tr.euronews.com/2023/02/28/kahramanmaras-depremleri-sonrasi-suriyede-kolera",
            ["kahramanmaras", "depremleri", "sonrasi", "suriyede", "kolera"],
        ),
        (  # TRT Haber: .html and an id
            "https://www.trthaber.com/haber/gundem/vanda-cig-faciasi-458812.html",
            ["vanda", "cig", "faciasi"],
        ),
        (  # CNN Türk: numbers inside the slug stay
            "https://www.cnnturk.com/turkiye/afad-duyurdu-akdenizde-4-1-buyuklugunde-deprem-3490067",
            ["afad", "duyurdu", "akdenizde", "4", "1", "buyuklugunde", "deprem"],
        ),
        (  # Milliyet
            "https://www.milliyet.com.tr/gundem/afad-sicak-gelismeyi-duyurdu-mugla-aciklarinda-deprem-7695882",
            ["afad", "sicak", "gelismeyi", "duyurdu", "mugla", "aciklarinda", "deprem"],
        ),
    ],
    ids=["cumhuriyet", "euronews", "trt-haber", "cnn-turk", "milliyet"],
)
def test_slug_tokens_for_each_outlets_url_shape(url: str, expected: list[str]) -> None:
    assert url_slug_tokens(url) == expected


def test_a_numeric_last_segment_falls_back_to_the_slug_before_it() -> None:
    assert url_slug_tokens("https://x.example/haber/deprem-bolgesinde-son-durum/123456") == [
        "deprem",
        "bolgesinde",
        "son",
        "durum",
    ]


def test_a_trailing_slash_query_string_and_fragment_are_ignored() -> None:
    assert url_slug_tokens("https://x.example/gundem/sel-uyarisi/?utm_source=x#top") == [
        "sel",
        "uyarisi",
    ]


@pytest.mark.parametrize("ending", [".htm", ".html", ".amp", ".HTML"])
def test_page_extensions_are_removed(ending: str) -> None:
    assert url_slug_tokens(f"https://x.example/heyelan-uyarisi-99{ending}") == [
        "heyelan",
        "uyarisi",
    ]


def test_percent_encoded_turkish_letters_are_decoded_and_folded() -> None:
    assert url_slug_tokens("https://x.example/haber/%C3%A7%C4%B1%C4%9F-d%C3%BC%C5%9Ft%C3%BC") == [
        "cig",
        "dustu",
    ]


def test_a_url_without_a_path_has_no_tokens() -> None:
    assert url_slug_tokens("https://x.example/") == []


def test_turkish_keywords_match_their_folded_form_in_urls() -> None:
    url = "https://tr.euronews.com/2023/02/28/kahramanmaras-depremleri-sonrasi"
    match = KeywordQuery(["Kahramanmaraş"]).match(url=url)[0]
    assert (match.field, match.token, match.mode) == ("url", "kahramanmaras", "prefix")


@pytest.mark.parametrize(
    ("keyword", "slug", "expected"),
    [
        ("çığ", "vanda-ciga-yakalandilar", True),
        ("çığ", "cocuk-ciglik-atti", False),
        ("sel", "rizede-selde-uc-kayip", True),
        ("sel", "bakan-selam-verdi", False),
        ("obruk", "konyada-obrugu-incelendi", True),
        ("göçük", "madendeki-gocugu-incelendi", True),
        ("toprak kayması", "rizede-toprak-kaymasi-yasandi", True),
    ],
)
def test_the_suffix_grammar_and_softening_work_on_folded_urls(
    keyword: str, slug: str, expected: bool
) -> None:
    url = f"https://www.example.com/haber/{slug}-123.html"
    assert bool(KeywordQuery([keyword]).match(url=url)) is expected


def test_category_folders_never_match() -> None:
    assert not KeywordQuery(["deprem"]).match(url="https://x.example/deprem/bakan-aciklama-yapti-5")


def test_fields_come_in_the_order_title_url_text() -> None:
    found = KeywordQuery(["deprem"]).match(
        text="Deprem raporu", url="https://x.example/deprem-raporu-1", title="Depremin ardından"
    )
    assert [m.field for m in found] == ["title", "url", "text"]
