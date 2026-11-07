"""Response.xml(): sitemaps parse, gzip included, and hostile XML can't expand or reach out."""

from __future__ import annotations

import gzip
import zlib
from collections.abc import Callable
from pathlib import Path

import pytest
from lxml import etree
from requests_mock import Mocker

from tr_news_scraper._http import Http
from tr_news_scraper.errors import ResponseTooLarge

REAL_SITEMAP = Path(__file__).parent / "fixtures" / "cumhuriyet-posts-2023-2.xml"
SITEMAP_URL = "https://news.example.com/sitemaps/posts-2023-2.xml"
ALLOWED = {"news.example.com"}
NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
SITEMAP = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://news.example.com/turkiye/kahramanmarasta-deprem-2045001</loc>
       <lastmod>2023-02-06T04:30:00+03:00</lastmod></url>
  <url><loc>https://news.example.com/siyaset/meclis-gundemi-2045002</loc>
       <lastmod>2023-02-06T09:00:00+03:00</lastmod></url>
</urlset>"""
BILLION_LAUGHS = b"""<?xml version="1.0"?>
<!DOCTYPE lolz [
  <!ENTITY lol "lol">
  <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
  <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
  <!ENTITY lol4 "&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;">
  <!ENTITY lol5 "&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;">
  <!ENTITY lol6 "&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;">
  <!ENTITY lol7 "&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;">
  <!ENTITY lol8 "&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;">
  <!ENTITY lol9 "&lol8;&lol8;&lol8;&lol8;&lol8;&lol8;&lol8;&lol8;&lol8;&lol8;">
]>
<urlset><url><loc>&lol9;</loc></url></urlset>"""


def fetch_xml(
    make_http: Callable[..., Http], mock: Mocker, body: bytes, **config: int
) -> etree._Element:
    mock.get(SITEMAP_URL, content=body)
    return make_http(**config).get(SITEMAP_URL, allowed_hosts=ALLOWED).xml()


def test_a_sitemap_parses(make_http: Callable[..., Http], requests_mock: Mocker) -> None:
    root = fetch_xml(make_http, requests_mock, SITEMAP)
    locs = root.xpath("//sm:loc/text()", namespaces=NS)
    assert locs == [
        "https://news.example.com/turkiye/kahramanmarasta-deprem-2045001",
        "https://news.example.com/siyaset/meclis-gundemi-2045002",
    ]


@pytest.mark.parametrize("gzipped", [False, True])
def test_a_real_cumhuriyet_archive_sitemap_parses(
    make_http: Callable[..., Http], requests_mock: Mocker, gzipped: bool
) -> None:
    body = REAL_SITEMAP.read_bytes()
    root = fetch_xml(make_http, requests_mock, gzip.compress(body) if gzipped else body)
    lastmods = root.xpath("//sm:lastmod/text()", namespaces=NS)
    assert len(lastmods) == 3
    assert all(stamp.startswith("2023-02-28T") for stamp in lastmods)


def test_a_gzipped_sitemap_file_parses(
    make_http: Callable[..., Http], requests_mock: Mocker
) -> None:
    root = fetch_xml(make_http, requests_mock, gzip.compress(SITEMAP))
    assert len(root.xpath("//sm:url", namespaces=NS)) == 2


def test_entities_are_never_expanded(make_http: Callable[..., Http], requests_mock: Mocker) -> None:
    # The libxml2 bundled with lxml refuses this document ("entity amplification"); a build
    # without that guard must still return the tree with nothing expanded. Both are safe.
    try:
        root = fetch_xml(make_http, requests_mock, BILLION_LAUGHS)
    except etree.XMLSyntaxError as refusal:
        refused_because = str(refusal)
    else:
        assert len(etree.tostring(root)) < 2_000
        assert "lollol" not in "".join(root.itertext())
        return
    assert "amplification" in refused_because


def test_external_entities_are_never_loaded(
    make_http: Callable[..., Http], requests_mock: Mocker, tmp_path: Path
) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP-SECRET-VALUE", encoding="utf-8")
    hostile = (
        f'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY leak SYSTEM "{secret.as_uri()}">'
        '<!ENTITY remote SYSTEM "https://evil.example.com/steal">]>'
        "<urlset><url><loc>&leak;&remote;</loc></url></urlset>"
    ).encode()
    root = fetch_xml(make_http, requests_mock, hostile)
    assert b"TOP-SECRET-VALUE" not in etree.tostring(root)
    assert "evil.example.com" not in {r.hostname for r in requests_mock.request_history}


def test_a_gzip_file_that_expands_past_the_cap_is_refused(
    make_http: Callable[..., Http], requests_mock: Mocker
) -> None:
    compressor = zlib.compressobj(9, zlib.DEFLATED, 31)
    bomb = (
        b"".join(compressor.compress(b"\0" * 1024 * 1024) for _ in range(16)) + compressor.flush()
    )
    requests_mock.get(SITEMAP_URL, content=bomb)
    response = make_http(max_bytes=4 * 1024 * 1024).get(SITEMAP_URL, allowed_hosts=ALLOWED)
    with pytest.raises(ResponseTooLarge):
        response.xml()


def test_malformed_xml_raises_a_syntax_error(
    make_http: Callable[..., Http], requests_mock: Mocker
) -> None:
    with pytest.raises(etree.XMLSyntaxError):
        fetch_xml(make_http, requests_mock, b"<urlset><url>")
