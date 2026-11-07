"""Outlet definitions: checked when they're created, so a typo fails early and clearly."""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from tr_news_scraper.outlets import Candidate, Month, MonthlySitemap, SiteSearch

SITEMAP: dict[str, Any] = {
    "id": "ornek-gazete",
    "name": "Örnek Gazete",
    "index": "https://www.example.com.tr/sitemaps/posts.xml",
    "month_file": r"/sitemaps/posts-(?P<year>\d{4})-(?P<month>\d{2})\.xml$",
}
SEARCH: dict[str, Any] = {
    "id": "ornek-arama",
    "name": "Örnek Arama",
    "url": "https://www.example.com.tr/api/search?q={query}&page={page}",
    "item": "//div[@class='result']",
    "link": ".//a/@href",
    "date": ".//span[@class='date']",
    "date_format": "%d.%m.%Y",
    "title": ".//a",
}


def sitemap(**changes: Any) -> MonthlySitemap:
    return MonthlySitemap(**(SITEMAP | changes))


def search(**changes: Any) -> SiteSearch:
    return SiteSearch(**(SEARCH | changes))


def test_a_monthly_sitemap_knows_its_hosts_and_method() -> None:
    outlet = sitemap(extra_hosts={"Static.Example.com.tr"})
    assert outlet.hosts == {"www.example.com.tr", "static.example.com.tr"}
    assert outlet.method == "monthly sitemap"
    assert outlet.pattern.search("https://www.example.com.tr/sitemaps/posts-2023-02.xml")


def test_a_site_search_knows_its_hosts_and_method() -> None:
    outlet = search()
    assert outlet.hosts == {"www.example.com.tr"}
    assert outlet.method == "site search"
    assert set(outlet.xpaths) == {"item", "link", "date", "title"}


def test_definitions_are_frozen() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        sitemap().index = "https://evil.example/"  # type: ignore[misc]


@pytest.mark.parametrize("bad_id", ["", "TRT", "trt_haber", "trt haber", "-trt", "trt-", "trt--x"])
def test_ids_must_be_lowercase_kebab_case(bad_id: str) -> None:
    with pytest.raises(ValueError, match="id must be lowercase kebab-case"):
        sitemap(id=bad_id)


def test_names_cant_be_blank() -> None:
    with pytest.raises(ValueError, match="name can't be blank"):
        search(name="  ")


@pytest.mark.parametrize(
    "bad_url",
    [
        "http://www.example.com.tr/sitemaps/posts.xml",
        "https://user:secret@www.example.com.tr/sitemaps/posts.xml",
        "https://10.0.0.8/sitemaps/posts.xml",
        "www.example.com.tr/sitemaps/posts.xml",
    ],
)
def test_the_index_must_be_https_on_a_public_host(bad_url: str) -> None:
    with pytest.raises(ValueError, match="index must be an https URL"):
        sitemap(index=bad_url)


def test_month_file_must_be_a_regex_with_year_and_month_groups() -> None:
    with pytest.raises(ValueError, match="month_file isn't a valid regular expression"):
        sitemap(month_file="posts-(")
    with pytest.raises(ValueError, match="named groups 'year' and 'month'"):
        sitemap(month_file=r"posts-(\d{4})-(\d{2})\.xml")


def test_titles_and_earliest_are_checked() -> None:
    with pytest.raises(ValueError, match="titles must be"):
        sitemap(titles="news")
    with pytest.raises(ValueError, match="earliest must be a Month"):
        sitemap(earliest="2010-12")
    assert sitemap(earliest=Month(2010, 12), titles="image").earliest == Month(2010, 12)


@pytest.mark.parametrize("bad_hosts", ["static.example.com.tr", ["ok.example", ""], [None]])
def test_extra_hosts_must_be_host_names(bad_hosts: Any) -> None:
    with pytest.raises(ValueError, match="extra_hosts"):
        sitemap(extra_hosts=bad_hosts)


@pytest.mark.parametrize("placeholder", ["{query}", "{page}"])
def test_the_search_url_needs_both_placeholders(placeholder: str) -> None:
    with pytest.raises(ValueError, match=f"url must contain {placeholder}"):
        search(url=SEARCH["url"].replace(placeholder, "x"))


def test_the_search_url_must_be_https() -> None:
    with pytest.raises(ValueError, match="url must be an https URL"):
        search(url="http://www.example.com.tr/search?q={query}&page={page}")


@pytest.mark.parametrize("field", ["item", "link", "date", "title"])
def test_xpaths_must_compile(field: str) -> None:
    with pytest.raises(ValueError, match=f"{field} isn't a valid XPath"):
        search(**{field: "//div[@class="})


@pytest.mark.parametrize("bad_format", ["%Y", "%d.%m", "%d.%m.%y.%Q", "no directives"])
def test_the_date_format_must_read_a_full_date(bad_format: str) -> None:
    with pytest.raises(ValueError, match="date_format must read a full date"):
        search(date_format=bad_format)


@pytest.mark.parametrize("bad_pages", [0, -1, 2.5, True])
def test_max_pages_must_be_a_positive_whole_number(bad_pages: Any) -> None:
    with pytest.raises(ValueError, match="max_pages"):
        search(max_pages=bad_pages)


@pytest.mark.parametrize(
    ("url", "accepted"),
    [
        ("https://www.example.com.tr/gundem/deprem-123", True),
        ("https://WWW.EXAMPLE.COM.TR/gundem/deprem-123", True),
        ("https://static.example.com.tr/a.jpg", True),
        ("http://www.example.com.tr/gundem/deprem-123", False),
        ("https://other.example/gundem/deprem-123", False),
        ("https://user@www.example.com.tr/x", False),
        ("https://[::1/x", False),
        ("not a url", False),
        ("", False),
    ],
)
def test_article_urls_must_be_https_on_the_outlets_hosts(url: str, accepted: bool) -> None:
    outlet = sitemap(extra_hosts=frozenset({"static.example.com.tr"}))
    assert outlet.accepts(url) is accepted


def test_internationalized_host_names_are_compared_in_idna_form() -> None:
    outlet = sitemap(index="https://haber.örnek.example/sitemaps/posts.xml")
    assert outlet.hosts == {"haber.xn--rnek-4qa.example"}
    assert outlet.accepts("https://haber.örnek.example/gundem/deprem-1")
    assert outlet.accepts("https://haber.xn--rnek-4qa.example/gundem/deprem-1")


def test_a_candidate_needs_only_an_outlet_url_and_month() -> None:
    candidate = Candidate("ornek-gazete", "https://www.example.com.tr/a-1", Month(2023, 2))
    assert (candidate.title, candidate.day, candidate.lastmod, candidate.source) == (
        None,
        None,
        None,
        "",
    )
