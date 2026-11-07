"""Reading monthly sitemaps: listed months, planning a range, and one month's articles."""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta, timezone

import pytest
from lxml import etree

from tr_news_scraper._http.safety import parse_xml
from tr_news_scraper.outlets import Month, MonthlySitemap
from tr_news_scraper.outlets._model import Gap
from tr_news_scraper.outlets._sitemaps import (
    Read,
    SitemapError,
    listed_months,
    plan_months,
    read_month_file,
)

NS = 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'
IMAGE_NS = 'xmlns:image="http://www.google.com/schemas/sitemap-image/1.1"'
OUTLET = MonthlySitemap(
    id="ornek",
    name="Örnek",
    index="https://www.example.com.tr/sitemaps/posts.xml",
    month_file=r"/sitemaps/posts-(?P<year>\d{4})-(?P<month>\d{1,2})\.xml$",
)
WITH_TITLES = MonthlySitemap(
    id="ornek",
    name="Örnek",
    index="https://www.example.com.tr/sitemaps/posts.xml",
    month_file=r"/sitemaps/posts-(?P<year>\d{4})-(?P<month>\d{1,2})\.xml$",
    titles="image",
)
FEBRUARY = Month(2023, 2)
SOURCE = "https://www.example.com.tr/sitemaps/posts-2023-2.xml"


def xml(text: str) -> bytes:
    return f'<?xml version="1.0" encoding="UTF-8"?>{text}'.encode()


def index_of(*locs: str, namespace: str = NS) -> bytes:
    entries = "".join(f"<sitemap><loc>{loc}</loc></sitemap>" for loc in locs)
    return xml(f"<sitemapindex {namespace}>{entries}</sitemapindex>")


def parse(content: bytes) -> etree._Element:
    return parse_xml(content, max_bytes=64 * 1024**2, url="https://www.example.com.tr/test.xml")


def test_the_index_gives_each_listed_month_and_its_file() -> None:
    index = index_of(
        "https://www.example.com.tr/sitemaps/posts-2026-11.xml",
        "  https://www.example.com.tr/sitemaps/posts-2023-2.xml\n",
        "https://www.example.com.tr/sitemaps/posts-1962-8.xml",
    )
    assert listed_months(parse(index), OUTLET) == {
        Month(2026, 11): "https://www.example.com.tr/sitemaps/posts-2026-11.xml",
        Month(2023, 2): "https://www.example.com.tr/sitemaps/posts-2023-2.xml",
        Month(1962, 8): "https://www.example.com.tr/sitemaps/posts-1962-8.xml",
    }


def test_index_entries_that_arent_month_files_are_ignored() -> None:
    index = index_of(
        "https://www.example.com.tr/feeds/sitemappages",
        "https://www.example.com.tr/sitemaps/posts-2023-13.xml",
        "https://www.example.com.tr/sitemaps/posts-2023-0.xml",
        "",
        "https://www.example.com.tr/sitemaps/posts-2023-2.xml",
    )
    assert list(listed_months(parse(index), OUTLET)) == [FEBRUARY]


def test_a_month_listed_twice_keeps_its_first_file() -> None:
    index = index_of(
        "https://www.example.com.tr/sitemaps/posts-2023-2.xml",
        "https://www.example.com.tr/sitemaps/posts-2023-02.xml",
    )
    assert listed_months(parse(index), OUTLET)[FEBRUARY].endswith("posts-2023-2.xml")


def test_an_index_without_a_namespace_is_read_too() -> None:
    index = index_of("https://www.example.com.tr/sitemaps/posts-2023-2.xml", namespace="")
    assert list(listed_months(parse(index), OUTLET)) == [FEBRUARY]


def test_a_list_of_urls_isnt_an_index() -> None:
    with pytest.raises(SitemapError, match="expected a sitemap index, found <urlset>"):
        listed_months(parse(xml(f"<urlset {NS}></urlset>")), OUTLET)


def test_planning_reads_listed_months_and_explains_the_rest() -> None:
    listed = {
        Month(2023, 1): "jan.xml",
        Month(2023, 3): "mar.xml",
        Month(2023, 5): "may.xml",
    }
    assert plan_months(listed, date(2022, 12, 15), date(2023, 6, 10)) == [
        Gap("before-archive", "the archive starts in 2023-01", month=Month(2022, 12)),
        Read(Month(2023, 1), "jan.xml"),
        Gap("not-in-archive", "the archive has no file for 2023-02", month=Month(2023, 2)),
        Read(Month(2023, 3), "mar.xml"),
        Gap("not-in-archive", "the archive has no file for 2023-04", month=Month(2023, 4)),
        Read(Month(2023, 5), "may.xml"),
        Gap("after-archive", "the archive ends in 2023-05", month=Month(2023, 6)),
    ]


def test_an_index_that_lists_nothing_leaves_every_month_unread() -> None:
    assert plan_months({}, date(2023, 2, 1), date(2023, 3, 1)) == [
        Gap("not-in-archive", "the archive lists no months", month=FEBRUARY)
    ]


def month_file(*entries: str) -> bytes:
    return xml(f"<urlset {NS} {IMAGE_NS}>{''.join(entries)}</urlset>")


def url_entry(loc: str, lastmod: str | None = None, image_title: str | None = None) -> str:
    parts = [f"<loc>{loc}</loc>"]
    if lastmod is not None:
        parts.append(f"<lastmod>{lastmod}</lastmod>")
    if image_title is not None:
        parts.append(
            "<image:image><image:loc>https://img.example/a.jpg</image:loc>"
            f"<image:title>{image_title}</image:title></image:image>"
        )
    return f"<url>{''.join(parts)}<changefreq>yearly</changefreq></url>"


def test_a_month_file_gives_one_candidate_per_url() -> None:
    content = month_file(
        url_entry("https://www.example.com.tr/gundem/deprem-1", "2023-02-06T04:30:00+03:00"),
        url_entry("https://www.example.com.tr/spor/mac-2"),
    )
    found = read_month_file(parse(content), OUTLET, FEBRUARY, SOURCE)
    assert [(c.url, c.month, c.source, c.outlet) for c in found.candidates] == [
        ("https://www.example.com.tr/gundem/deprem-1", FEBRUARY, SOURCE, "ornek"),
        ("https://www.example.com.tr/spor/mac-2", FEBRUARY, SOURCE, "ornek"),
    ]
    assert found.candidates[0].lastmod == datetime(
        2023, 2, 6, 4, 30, tzinfo=timezone(timedelta(hours=3))
    )
    assert found.candidates[1].lastmod is None
    assert (found.entries, found.dropped) == (2, 0)


def test_whitespace_around_urls_is_removed() -> None:
    # Star writes <loc> https://... </loc>.
    content = month_file(url_entry("\n  https://www.example.com.tr/dunya/haber-1770667/  "))
    found = read_month_file(parse(content), OUTLET, FEBRUARY, SOURCE)
    assert found.candidates[0].url == "https://www.example.com.tr/dunya/haber-1770667/"


@pytest.mark.parametrize(
    "loc",
    [
        "http://www.example.com.tr/gundem/deprem-1",
        "https://www.elsewhere.example/gundem/deprem-1",
        "https://user:pw@www.example.com.tr/gundem/deprem-1",
        "",
        "   ",
    ],
)
def test_entries_off_the_outlets_https_hosts_are_dropped_and_counted(loc: str) -> None:
    content = month_file(url_entry(loc), url_entry("https://www.example.com.tr/a-1"))
    found = read_month_file(parse(content), OUTLET, FEBRUARY, SOURCE)
    assert [c.url for c in found.candidates] == ["https://www.example.com.tr/a-1"]
    assert (found.entries, found.dropped) == (2, 1)


def test_image_titles_are_headlines_only_when_the_outlet_says_so() -> None:
    content = month_file(
        url_entry("https://www.example.com.tr/a-1", image_title="Pentagon:\n  Rusya yarışa  "),
        url_entry("https://www.example.com.tr/a-2", image_title="   "),
        url_entry("https://www.example.com.tr/a-3"),
    )
    with_titles = read_month_file(parse(content), WITH_TITLES, FEBRUARY, SOURCE)
    assert [c.title for c in with_titles.candidates] == ["Pentagon: Rusya yarışa", None, None]
    without = read_month_file(parse(content), OUTLET, FEBRUARY, SOURCE)
    assert [c.title for c in without.candidates] == [None, None, None]


def test_headlines_are_nfc_normalized() -> None:
    decomposed = "Kahramanmaraş"  # ş as s + combining cedilla
    content = month_file(url_entry("https://www.example.com.tr/a-1", image_title=decomposed))
    found = read_month_file(parse(content), WITH_TITLES, FEBRUARY, SOURCE)
    assert found.candidates[0].title == "Kahramanmaraş"


def test_an_index_isnt_a_month_file() -> None:
    with pytest.raises(SitemapError, match=r"expected a list of URLs \(<urlset>\)"):
        read_month_file(parse(index_of("https://x.example/a.xml")), OUTLET, FEBRUARY, SOURCE)


def test_an_empty_month_file_has_no_candidates() -> None:
    found = read_month_file(parse(month_file()), OUTLET, FEBRUARY, SOURCE)
    assert (found.candidates, found.entries, found.dropped) == ([], 0, 0)


# The budget covers parsing as users run it; coverage tracing would roughly double it before 3.14.
@pytest.mark.no_cover
def test_a_10000_entry_month_file_is_read_in_under_a_second() -> None:
    entries = [
        url_entry(
            f"https://www.example.com.tr/gundem/kahramanmarasta-deprem-sonrasi-{n}",
            "2023-02-06T04:30:00+03:00",
            "Kahramanmaraş'ta deprem sonrası",
        )
        for n in range(10_000)
    ]
    content = month_file(*entries)
    started = time.perf_counter()
    found = read_month_file(parse(content), WITH_TITLES, FEBRUARY, SOURCE)
    elapsed = time.perf_counter() - started
    assert len(found.candidates) == 10_000
    assert elapsed < 1.0, f"took {elapsed:.2f} s"
