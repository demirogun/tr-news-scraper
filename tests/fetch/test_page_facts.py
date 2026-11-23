"""A page's own statements about its article (F3b, F3d, F3e): headline, lead and author."""

from __future__ import annotations

import json
import unicodedata
from datetime import datetime
from typing import Any

import pytest

from tr_news_scraper._structured import (
    PageFacts,
    choose_author,
    choose_headline,
    clean_headline,
    read_page,
    with_lead,
)
from tr_news_scraper.outlets._dates import ISTANBUL

LEAD = "Kahramanmaraş merkezli depremlerin ardından bölgedeki okullarda eğitim yeniden başladı."
BODY = "<p>Birinci paragraf.</p><p>İkinci paragraf.</p>"


def page(
    *,
    article: dict[str, Any] | None = None,
    head: str = "",
    body: str = BODY,
) -> str:
    data = "" if article is None else json.dumps(article, ensure_ascii=False)
    script = "" if article is None else f'<script type="application/ld+json">{data}</script>'
    return f"<html><head><title>Örnek</title>{head}{script}</head><body>{body}</body></html>"


def news(**fields: Any) -> dict[str, Any]:
    return {"@context": "https://schema.org", "@type": "NewsArticle", **fields}


def test_a_page_with_json_ld_states_its_facts() -> None:
    facts = read_page(
        page(
            article=news(
                headline="Okullarda  eğitim başladı",
                datePublished="2023-02-20T09:15:00+03:00",
                dateModified="2023-02-21T10:00:00+03:00",
                description=LEAD,
                author={"@type": "Person", "name": "Ayşe Demir"},
                publisher={"@type": "Organization", "name": "Örnek Gazetesi"},
            ),
            head='<meta property="og:title" content="Okullarda eğitim başladı - Örnek">',
            body=f"<h1>Okullarda eğitim başladı</h1><h2>{LEAD}</h2>{BODY}",
        )
    )
    assert facts == PageFacts(
        article=True,
        headline="Okullarda eğitim başladı",
        published=datetime(2023, 2, 20, 9, 15, tzinfo=ISTANBUL),
        authors=("Ayşe Demir",),
        publisher="Örnek Gazetesi",
        description=LEAD,
        h1s=("Okullarda eğitim başladı",),
        og_title="Okullarda eğitim başladı - Örnek",
        lead=LEAD,
    )


def test_a_page_without_json_ld_states_only_its_tags() -> None:
    facts = read_page(
        page(
            head=f'<meta name="description" content="{LEAD}">',
            body=f"<h1>Başlık</h1><p>{LEAD}</p>",
        )
    )
    assert (facts.article, facts.headline, facts.published, facts.authors) == (
        False,
        None,
        None,
        (),
    )
    assert (facts.description, facts.lead, facts.h1s) == (LEAD, LEAD, ("Başlık",))


@pytest.mark.parametrize("html", ["", "   ", "<html></html>", "<?xml version='1.0'?><a/>"])
def test_an_empty_or_odd_page_states_nothing(html: str) -> None:
    facts = read_page(html)
    assert (facts.article, facts.headline, facts.lead) == (False, None, None)


def test_a_page_declaring_another_encoding_is_read_as_the_text_given() -> None:
    html = page(
        article=news(headline="Şişli'de çığ"),
        head='<meta charset="windows-1254">',
    )
    assert read_page(html).headline == "Şişli'de çığ"


# Headline (F3b)


def facts_with(**fields: Any) -> PageFacts:
    return PageFacts(**fields)


def test_the_h1_wins_when_it_equals_the_json_ld_headline() -> None:
    facts = facts_with(headline="Göl çamura bulandı", h1s=("Göl  çamura bulandı",))
    assert choose_headline(facts, "Göl çamura bulandı | STAR", "Star") == "Göl  çamura bulandı"


def test_the_h1_wins_when_it_equals_og_title() -> None:
    facts = facts_with(
        headline="Göl bulandı (video)", og_title="Göl çamura bulandı", h1s=("Göl çamura bulandı",)
    )
    assert choose_headline(facts, None, "Star") == "Göl çamura bulandı"


def test_the_h1_wins_when_it_equals_trafilaturas_title_without_the_outlets_name() -> None:
    facts = facts_with(h1s=("Hatay'da deprem",))
    assert choose_headline(facts, "Hatay'da deprem - Sözcü Gazetesi", "Sözcü") == "Hatay'da deprem"


def test_texts_are_compared_after_nfc() -> None:
    decomposed = unicodedata.normalize("NFD", "Şişli'de çığ")
    facts = facts_with(headline="Şişli'de çığ", h1s=(decomposed,))
    assert choose_headline(facts, None, "Örnek") == decomposed


def test_a_later_h1_counts_when_the_first_is_the_sites_logo() -> None:
    facts = facts_with(headline="Göl çamura bulandı", h1s=("Örnek Haber", "Göl çamura bulandı"))
    assert choose_headline(facts, None, "Örnek") == "Göl çamura bulandı"


def test_an_h1_that_matches_no_candidate_gives_way_to_the_json_ld_headline() -> None:
    facts = facts_with(headline="Göl çamura bulandı", h1s=("Son dakika haberleri",))
    assert choose_headline(facts, "Göl bulandı | STAR", "Star") == "Göl çamura bulandı"


def test_without_a_json_ld_headline_trafilaturas_title_stays() -> None:
    facts = facts_with(h1s=("Son dakika haberleri",))
    assert choose_headline(facts, "Göl bulandı | STAR", "Star") == "Göl bulandı | STAR"
    assert choose_headline(PageFacts(), None, "Star") is None


# Lead (F3d)


def test_a_visible_lead_matching_the_description_is_put_first() -> None:
    facts = read_page(page(article=news(description=LEAD), body=f"<h2>{LEAD}</h2>{BODY}"))
    assert facts.lead == LEAD
    assert with_lead("Birinci paragraf.\nİkinci paragraf.", facts.lead) == (
        f"{LEAD}\nBirinci paragraf.\nİkinci paragraf."
    )


@pytest.mark.parametrize("tag", ["h2", "h3", "p", "div", "span", "strong"])
def test_the_lead_may_be_in_any_of_six_elements(tag: str) -> None:
    facts = read_page(page(article=news(description=LEAD), body=f"<{tag}>{LEAD}</{tag}>"))
    assert facts.lead == LEAD


def test_a_lead_98_percent_like_the_description_counts_and_its_visible_text_is_used() -> None:
    shown = LEAD.replace("yeniden", "yeni den")
    facts = read_page(page(article=news(description=LEAD), body=f"<h2>  {shown} </h2>{BODY}"))
    assert facts.lead == shown


def test_a_lead_less_alike_than_that_doesnt_count() -> None:
    shown = LEAD.replace("okullarda eğitim yeniden", "üniversitelerde dersler")
    facts = read_page(page(article=news(description=LEAD), body=f"<h2>{shown}</h2>{BODY}"))
    assert facts.lead is None


def test_og_description_or_the_description_tag_stand_in_for_json_ld() -> None:
    og = read_page(
        page(head=f'<meta property="og:description" content="{LEAD}">', body=f"<h2>{LEAD}</h2>")
    )
    plain = read_page(
        page(head=f'<meta name="description" content="{LEAD}">', body=f"<p>{LEAD}</p>")
    )
    assert (og.lead, plain.lead) == (LEAD, LEAD)


def test_json_ld_description_comes_before_the_meta_tags() -> None:
    facts = read_page(
        page(
            article=news(description=LEAD),
            head='<meta property="og:description" content="Başka bir özet metni.">',
        )
    )
    assert facts.description == LEAD


@pytest.mark.parametrize(
    "body",
    [
        BODY,
        f"<div hidden><p>{LEAD}</p></div>{BODY}",
        f'<div style="display: none"><h2>{LEAD}</h2></div>{BODY}',
        f"<noscript><p>{LEAD}</p></noscript>{BODY}",
        f"<template><p>{LEAD}</p></template>{BODY}",
    ],
    ids=["absent", "hidden", "display-none", "noscript", "template"],
)
def test_a_description_that_isnt_visible_is_never_added(body: str) -> None:
    facts = read_page(page(article=news(description=LEAD), body=body))
    assert facts.lead is None
    assert with_lead("Birinci paragraf.", facts.lead) == "Birinci paragraf."


def test_a_description_that_repeats_the_headline_isnt_a_lead() -> None:
    title = "Okullarda eğitim yeniden başladı"
    facts = read_page(
        page(
            article=news(headline=title, description=title),
            body=f"<div class='title'><h1>{title}</h1></div>{BODY}",
        )
    )
    assert facts.lead is None


@pytest.mark.parametrize(
    "text",
    [
        f"{LEAD}\nBirinci paragraf.",
        f"{LEAD} Birinci paragrafın devamı.\nİkinci paragraf.",
        f"{LEAD.replace('yeniden', 'yeni den')}\nBirinci paragraf.",
        f"Okullarda eğitim başladı\n{LEAD}\nBirinci paragraf.",
        f"Okullarda eğitim başladı\n{LEAD.replace('yeniden', 'yeni den')}\nBirinci paragraf.",
        f"Birinci paragraf. {LEAD} Devamı.",
    ],
    ids=[
        "first-line",
        "start-of-first-line",
        "98-percent",
        "after-the-headline",
        "98-percent-later",
        "inside-a-paragraph",
    ],
)
def test_a_lead_the_text_already_has_isnt_added_again(text: str) -> None:
    assert with_lead(text, LEAD) == text


def test_without_text_there_is_nothing_to_put_a_lead_in_front_of() -> None:
    assert with_lead(None, LEAD) is None


# Author (F3e)


@pytest.mark.parametrize(
    ("author", "expected"),
    [
        ({"@type": "Person", "name": "Ayşe Demir"}, ("Ayşe Demir",)),
        ("Ayşe Demir", ("Ayşe Demir",)),
        (
            [
                {"@type": "Person", "name": "Ayşe Demir"},
                {"@type": "Person", "name": "Deniz Yılmaz"},
            ],
            ("Ayşe Demir", "Deniz Yılmaz"),
        ),
        ([{"name": "Ayşe Demir"}, "AYŞE DEMİR", {"name": " Ayşe  Demir "}], ("Ayşe Demir",)),
        ({"@type": "Organization", "name": "Haber Merkezi"}, ("Haber Merkezi",)),
        (["https://www.ornek.com.tr/yazar/ayse-demir", {"url": "https://x"}, 7], ()),
        (None, ()),
        # Email addresses are left out of names, and so are names that are only an address.
        ({"name": "AYŞE DEMİR / cumartesi@ornek.com.tr"}, ("AYŞE DEMİR",)),
        ({"name": "Ayşe Demir (ayse.demir@ornek.com.tr)"}, ("Ayşe Demir",)),
        (["haber@ornek.com.tr", {"name": "Deniz Yılmaz"}], ("Deniz Yılmaz",)),
    ],
)
def test_json_ld_names_every_author_once(author: object, expected: tuple[str, ...]) -> None:
    assert read_page(page(article=news(author=author))).authors == expected


def test_several_authors_are_joined_by_commas() -> None:
    facts = facts_with(authors=("Ayşe Demir", "Deniz Yılmaz"), publisher="Örnek")
    assert choose_author(facts, "Elif Kaya", "Örnek") == "Ayşe Demir, Deniz Yılmaz"


def test_an_author_equal_to_the_publisher_or_outlet_is_dropped() -> None:
    facts = facts_with(authors=("TRT HABER", "Ayşe Demir"), publisher="TRT Haber")
    assert choose_author(facts, None, "TRT Haber") == "Ayşe Demir"
    only_outlet = facts_with(authors=("Sözcü",), publisher="Sözcü Gazetesi")
    assert choose_author(only_outlet, "Haber Merkezi", "Sözcü") == "Haber Merkezi"


def test_without_json_ld_authors_trafilaturas_byline_stays() -> None:
    assert choose_author(PageFacts(), "AYŞE DEMİR; Cumartesi Com Tr", "Akşam") == (
        "AYŞE DEMİR; Cumartesi Com Tr"
    )


def test_publisher_names_come_from_an_object_a_list_or_a_string() -> None:
    for publisher in ({"name": "Örnek"}, [{"name": "Örnek"}], "Örnek"):
        assert read_page(page(article=news(publisher=publisher))).publisher == "Örnek"


def test_clean_headline_needs_an_outlet_name_to_clean_anything() -> None:
    assert clean_headline("Hatay'da deprem - Sözcü Gazetesi", "") == (
        "Hatay'da deprem - Sözcü Gazetesi"
    )


def test_without_json_ld_the_open_graph_publication_time_counts() -> None:
    # Sputnik Türkiye's pages have no JSON-LD article and write the time in ISO 8601's basic
    # form, which htmldate doesn't read.
    head = '<meta property="article:published_time" content="20230228T2347+0300">'
    assert read_page(page(head=head)).published == datetime(2023, 2, 28, 23, 47, tzinfo=ISTANBUL)
    with_json_ld = read_page(
        page(article=news(datePublished="2023-02-27T10:00:00+03:00"), head=head)
    )
    assert with_json_ld.published == datetime(2023, 2, 27, 10, 0, tzinfo=ISTANBUL)
