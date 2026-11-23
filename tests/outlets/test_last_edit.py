"""Archives grouped by last edit (O3b): a month's articles, wherever their last edit put them."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from requests_mock import Mocker

from tr_news_scraper._http import Http
from tr_news_scraper.errors import OutletFailed
from tr_news_scraper.outlets import Month, MonthlySitemap
from tr_news_scraper.outlets._scan import scan
from tr_news_scraper.outlets._sitemaps import article_id

BASE = "https://www.example.com.tr"
INDEX = f"{BASE}/sitemap_posts.xml"
NS = 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'
TODAY = date(2026, 11, 7)
JAN, FEB, MAR, APR = Month(2023, 1), Month(2023, 2), Month(2023, 3), Month(2023, 4)
OUTLET = MonthlySitemap(
    id="ornek",
    name="Örnek",
    index=INDEX,
    month_file=r"/sitemap_post_(?P<year>\d{4})(?P<month>\d{2})\.xml$",
    grouping="last-edit",
    article_id=r"-(?P<id>\d+)$",
)
# The articles each month's file lists, by id: a file holds the articles last edited that month.
# 105 was published in January and edited in February; 115 and 118 were published in February
# and edited in March; "kunye" has no id.
FILES: dict[Month, list[int | str]] = {
    JAN: [100, 101, 102, 103, 104, 106, 107, 108, 109, 110, 50],
    FEB: [111, 112, 113, 114, 116, 117, 119, 120, 105, "kunye"],
    MAR: [115, 118, 121, 122, 123, 124, 125, "iletisim"],
    APR: [126, 127, 128],
}


def file_url(month: Month) -> str:
    return f"{BASE}/sitemap_post_{month.year}{month.month:02d}.xml"


def article(item: int | str) -> str:
    return f"{BASE}/gundem/haber-{item}" if isinstance(item, int) else f"{BASE}/{item}"


def serve(requests_mock: Mocker, *listed: Month, **responses: dict[str, Any]) -> None:
    """The index lists ``listed``; ``responses`` overrides a month's file by its name, "feb"."""
    entries = "".join(f"<sitemap><loc>{file_url(month)}</loc></sitemap>" for month in listed)
    requests_mock.get(
        INDEX, text=f'<?xml version="1.0"?><sitemapindex {NS}>{entries}</sitemapindex>'
    )
    for month in listed:
        items = "".join(f"<url><loc>{article(item)}</loc></url>" for item in FILES[month])
        default = {"text": f'<?xml version="1.0"?><urlset {NS}>{items}</urlset>'}
        name = month.start.strftime("%b").lower()
        requests_mock.get(file_url(month), **responses.get(name, default))


def archive_requests(requests_mock: Mocker) -> list[str]:
    return [r.url for r in requests_mock.request_history if not r.url.endswith("/robots.txt")]


def test_a_month_keeps_its_own_articles_and_those_edited_the_month_after(
    http: Http, requests_mock: Mocker
) -> None:
    serve(requests_mock, JAN, FEB, MAR, APR)
    found = scan(OUTLET, http, date(2023, 2, 1), date(2023, 3, 1), today=TODAY)
    candidates = list(found)
    own: list[int | str] = [111, 112, 113, 114, 116, 117, 119, 120, "kunye"]
    assert [c.url for c in candidates] == [article(item) for item in [*own, 115, 118]]
    assert {c.month for c in candidates} == {FEB}
    assert [c.source for c in candidates[-2:]] == [file_url(MAR)] * 2
    assert (found.months, found.gaps) == ([FEB], [])
    assert sorted(archive_requests(requests_mock)) == sorted(
        [INDEX, file_url(JAN), file_url(FEB), file_url(MAR)]
    )


def test_two_months_read_each_file_once_and_share_no_article(
    http: Http, requests_mock: Mocker
) -> None:
    serve(requests_mock, JAN, FEB, MAR, APR)
    found = scan(OUTLET, http, date(2023, 2, 1), date(2023, 4, 1), today=TODAY)
    by_month: dict[Month, list[str]] = {}
    for candidate in found:
        by_month.setdefault(candidate.month, []).append(candidate.url)
    march: list[int | str] = [121, 122, 123, 124, 125, "iletisim"]
    assert by_month[MAR] == [article(item) for item in march]
    assert article(115) in by_month[FEB]
    assert not set(by_month[FEB]) & set(by_month[MAR])
    requested = archive_requests(requests_mock)
    assert sorted(requested) == sorted(
        [INDEX, file_url(JAN), file_url(FEB), file_url(MAR), file_url(APR)]
    )
    assert found.months == [FEB, MAR]


def test_without_the_month_before_there_is_no_lower_end(http: Http, requests_mock: Mocker) -> None:
    serve(requests_mock, FEB, MAR)
    urls = [c.url for c in scan(OUTLET, http, date(2023, 2, 1), date(2023, 3, 1), today=TODAY)]
    assert article(105) in urls
    assert article(115) in urls


def test_the_newest_month_has_nothing_to_look_ahead_to(http: Http, requests_mock: Mocker) -> None:
    serve(requests_mock, JAN, FEB)
    found = scan(OUTLET, http, date(2023, 2, 1), date(2023, 3, 1), today=TODAY)
    urls = [c.url for c in found]
    assert article(105) not in urls
    assert article(115) not in urls
    assert (found.months, found.gaps) == ([FEB], [])


def test_when_the_month_after_fails_the_gap_says_what_may_be_missing(
    http: Http, requests_mock: Mocker
) -> None:
    serve(requests_mock, JAN, FEB, MAR, mar={"status_code": 404})
    found = scan(OUTLET, http, date(2023, 2, 1), date(2023, 3, 1), today=TODAY)
    urls = [c.url for c in found]
    assert len(urls) == 9
    [gap] = found.gaps
    assert (gap.reason, gap.month, gap.url) == ("failed", FEB, file_url(MAR))
    assert gap.detail == (
        "the file for 2023-03 couldn't be read: the request failed (HTTP 404, 1 attempt), so "
        "articles published in 2023-02 and edited later may be missing"
    )
    assert found.months == []


def test_when_the_month_before_fails_the_month_keeps_all_its_own_entries(
    http: Http, requests_mock: Mocker
) -> None:
    serve(requests_mock, JAN, FEB, MAR, jan={"status_code": 404})
    found = scan(OUTLET, http, date(2023, 2, 1), date(2023, 3, 1), today=TODAY)
    urls = [c.url for c in found]
    assert article(105) in urls
    assert article(115) in urls
    [gap] = found.gaps
    assert (gap.reason, gap.month, gap.url) == ("failed", FEB, file_url(JAN))
    assert gap.detail.endswith("so 2023-02 may include older articles last edited then")


def test_the_months_own_file_failing_is_the_usual_gap_and_no_neighbour_is_read(
    http: Http, requests_mock: Mocker
) -> None:
    serve(requests_mock, JAN, FEB, MAR, feb={"status_code": 404})
    found = scan(OUTLET, http, date(2023, 2, 1), date(2023, 3, 1), today=TODAY)
    with pytest.raises(OutletFailed):
        list(found)
    [gap] = found.gaps
    assert (gap.reason, gap.month, gap.url) == ("failed", FEB, file_url(FEB))
    assert archive_requests(requests_mock) == [INDEX, file_url(FEB)]


def test_an_article_id_is_a_number_found_in_the_url() -> None:
    assert article_id(OUTLET, f"{BASE}/gundem/haber-1234") == 1234
    assert article_id(OUTLET, f"{BASE}/kunye") is None
    plain = MonthlySitemap(id="ornek", name="Örnek", index=INDEX, month_file=OUTLET.month_file)
    assert article_id(plain, f"{BASE}/gundem/haber-1234") is None
    letters = MonthlySitemap(
        id="ornek",
        name="Örnek",
        index=INDEX,
        month_file=OUTLET.month_file,
        article_id=r"/(?P<id>[a-z]+)$",
    )
    assert article_id(letters, f"{BASE}/gundem/abc") is None
