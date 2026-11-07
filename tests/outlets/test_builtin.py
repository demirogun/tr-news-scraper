"""The built-in outlets, read from archive files recorded on 2026-11-07."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from requests_mock import Mocker

from tr_news_scraper._http import Http
from tr_news_scraper._http.safety import parse_xml
from tr_news_scraper.outlets import Month, MonthlySitemap, builtin, get
from tr_news_scraper.outlets._model import Gap
from tr_news_scraper.outlets._scan import scan
from tr_news_scraper.outlets._sitemaps import listed_months

FIXTURES = Path(__file__).parent / "fixtures"
TODAY = date(2026, 11, 7)
FEB_2023 = Month(2023, 2)

# outlet id, recorded month, its file URL, first and last article URL in the recorded file
RECORDED = [
    (
        "cumhuriyet",
        FEB_2023,
        "https://www.cumhuriyet.com.tr/sitemaps/posts-2023-2.xml",
        "https://www.cumhuriyet.com.tr/spor/leeds-uniteddan-nicolo-zaniolo-itirafi-istedik-ama-alamadik-2056370",
        "https://www.cumhuriyet.com.tr/kultur-sanat/kil-hamurundan-cok-daha-fazlasi-2026520",
    ),
    (
        "euronews-tr",
        FEB_2023,
        "https://tr.euronews.com/sitemap/articles-2023-02.xml",
        "https://tr.euronews.com/2023/02/28/elon-musktan-yapay-zeka-hamlesi-chatgptye-rakip-olmak-icin-ekip-kuruyor",
        "https://tr.euronews.com/2023/02/01/abd-temsilciler-meclisi-salgin-bitti-yasa-tasarisini-kabul-etti",
    ),
    (
        "trt-haber",
        FEB_2023,
        "https://www.trthaber.com/sitemaps/news-2023-02.xml",
        "https://www.trthaber.com/haber/guncel/mardinde-kaza-2-olu-2-yarali-750286.html",
        "https://www.trthaber.com/haber/gundem/bbp-genel-baskani-desticiye-taziye-mesajlari-742472.html",
    ),
    (
        "star",
        FEB_2023,
        "https://www.star.com.tr/sitemaps/posts-2023-02.xml",
        "https://www.star.com.tr/spor/mourinho-mauro-icardiyi-istiyor-tum-yollar-romaya-cikiyor-haber-1770668/",
        "https://www.star.com.tr/ekonomi/komsu-duyurdu-turkiye-ile-cok-girisli-vize-surecini-baslattik-haber-1764971/",
    ),
    (
        "aksam",
        FEB_2023,
        "https://www.aksam.com.tr/sitemaps/posts-2023-02.xml",
        "https://www.aksam.com.tr/dunya/abdden-rusya-aciklamasi-rusya-yarisa-girebilecek-durumda-degil/haber-1346851",
        "https://www.aksam.com.tr/guncel/eviniz-depreme-dayanikli-mi-adim-adim-hasar-tespiti/haber-1157527",
    ),
    (
        "sozcu",
        Month(2024, 6),
        "https://www.sozcu.com.tr/feeds/sitemapposts?year=2024&month=6",
        "https://www.sozcu.com.tr/hakkari-ye-kayyum-atandi-p54794",
        "https://www.sozcu.com.tr/abd-de-netanyahu-da-kongre-de-konusma-daveti-p53424",
    ),
]
SITEMAP_IDS = [case[0] for case in RECORDED]


@pytest.fixture(autouse=True)
def _builtin_hosts_have_no_robots_txt(requests_mock: Mocker) -> None:
    for outlet in builtin():
        for host in outlet.hosts:
            requests_mock.get(f"https://{host}/robots.txt", status_code=404)


def recorded(outlet_id: str, name: str) -> bytes:
    return (FIXTURES / outlet_id / name).read_bytes()


def sitemap(outlet_id: str) -> MonthlySitemap:
    outlet = get(outlet_id)
    assert isinstance(outlet, MonthlySitemap)
    return outlet


def test_the_built_in_outlets_come_in_a_fixed_order() -> None:
    assert [outlet.id for outlet in builtin()] == SITEMAP_IDS


def test_get_finds_an_outlet_by_id() -> None:
    assert get("trt-haber").name == "TRT Haber"


def test_get_names_the_valid_ids_for_an_unknown_one() -> None:
    with pytest.raises(ValueError, match=r"no built-in outlet 'hurriyet'; choose from cumhuriyet"):
        get("hurriyet")


def test_every_built_in_outlet_explains_its_coverage() -> None:
    for outlet in builtin():
        assert outlet.notes
        assert outlet.method == "monthly sitemap"


@pytest.mark.parametrize(
    ("outlet_id", "month", "file_url", "first", "last"), RECORDED, ids=SITEMAP_IDS
)
def test_each_outlet_reads_its_recorded_month(
    http: Http,
    requests_mock: Mocker,
    outlet_id: str,
    month: Month,
    file_url: str,
    first: str,
    last: str,
) -> None:
    outlet = sitemap(outlet_id)
    requests_mock.get(outlet.index, content=recorded(outlet_id, "index.xml"))
    requests_mock.get(file_url, content=recorded(outlet_id, f"{month}.xml"))
    found = scan(outlet, http, month.start, month.next().start, today=TODAY)
    candidates = list(found)
    assert len(candidates) == 20
    assert (candidates[0].url, candidates[-1].url) == (first, last)
    assert all(outlet.accepts(c.url) and c.url == c.url.strip() for c in candidates)
    assert {c.month for c in candidates} == {month}
    assert all(c.lastmod is not None and c.lastmod.utcoffset() is not None for c in candidates)
    assert (found.gaps, found.dropped) == ([], 0)


@pytest.mark.parametrize("outlet_id", SITEMAP_IDS)
def test_headlines_come_only_from_outlets_whose_image_titles_are_headlines(
    http: Http, requests_mock: Mocker, outlet_id: str
) -> None:
    [(_, month, file_url, *_)] = [case for case in RECORDED if case[0] == outlet_id]
    outlet = sitemap(outlet_id)
    requests_mock.get(outlet.index, content=recorded(outlet_id, "index.xml"))
    requests_mock.get(file_url, content=recorded(outlet_id, f"{month}.xml"))
    titles = [c.title for c in scan(outlet, http, month.start, month.next().start, today=TODAY)]
    if outlet_id == "star":
        assert all(titles)
        assert titles[1] == "Pentagon: Rusya yarışa girebilecek durumda değil"
    else:
        # Euronews's recorded file has image titles too, but they describe photos.
        assert titles == [None] * 20


@pytest.mark.parametrize("outlet_id", SITEMAP_IDS)
def test_each_recorded_index_starts_at_the_declared_earliest_month(outlet_id: str) -> None:
    outlet = sitemap(outlet_id)
    index = parse_xml(recorded(outlet_id, "index.xml"), max_bytes=10**7, url=outlet.index)
    listed = listed_months(index, outlet)
    assert min(listed) == outlet.earliest
    assert max(listed) == Month(2026, 11)


def test_sozcus_index_entries_that_arent_months_are_ignored() -> None:
    outlet = sitemap("sozcu")
    index = parse_xml(recorded("sozcu", "index.xml"), max_bytes=10**7, url=outlet.index)
    assert sorted(listed_months(index, outlet)) == [
        Month(2023, 12),
        Month(2024, 1),
        Month(2024, 6),
        Month(2026, 10),
        Month(2026, 11),
    ]


def test_a_range_across_three_months_reads_exactly_those_files(
    http: Http, requests_mock: Mocker
) -> None:
    outlet = sitemap("cumhuriyet")
    requests_mock.get(outlet.index, content=recorded("cumhuriyet", "index.xml"))
    base = "https://www.cumhuriyet.com.tr/sitemaps"
    empty = '<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"/>'
    requests_mock.get(f"{base}/posts-2023-1.xml", text=empty)
    requests_mock.get(f"{base}/posts-2023-2.xml", content=recorded("cumhuriyet", "2023-02.xml"))
    requests_mock.get(f"{base}/posts-2023-3.xml", text=empty)
    found = scan(outlet, http, date(2023, 1, 15), date(2023, 3, 10), today=TODAY)
    assert len(list(found)) == 20
    archive = [r.url for r in requests_mock.request_history if not r.url.endswith("robots.txt")]
    assert archive == [
        outlet.index,
        f"{base}/posts-2023-1.xml",
        f"{base}/posts-2023-2.xml",
        f"{base}/posts-2023-3.xml",
    ]


def test_sozcu_in_february_2023_reads_only_its_index(http: Http, requests_mock: Mocker) -> None:
    outlet = sitemap("sozcu")
    requests_mock.get(outlet.index, content=recorded("sozcu", "index.xml"))
    found = scan(outlet, http, date(2023, 2, 1), date(2023, 3, 1), today=TODAY)
    assert list(found) == []
    assert found.gaps == [Gap("before-archive", "the archive starts in 2023-12", month=FEB_2023)]
    archive = [r.url for r in requests_mock.request_history if not r.url.endswith("robots.txt")]
    assert archive == [outlet.index]
