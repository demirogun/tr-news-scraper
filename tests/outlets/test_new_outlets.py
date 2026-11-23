"""The outlets 1.1 adds, read from archive files recorded on 2026-11-23 (SPEC-1.1 P4)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from requests_mock import Mocker

from tr_news_scraper._http import Http
from tr_news_scraper._http.safety import parse_xml
from tr_news_scraper._search import collect
from tr_news_scraper._table import OutletRun, clean_url
from tr_news_scraper.matching import KeywordQuery
from tr_news_scraper.outlets import ChunkedSitemap, Month, MonthlySitemap, builtin, get
from tr_news_scraper.outlets._scan import scan
from tr_news_scraper.outlets._sitemaps import article_id

FIXTURES = Path(__file__).parent / "fixtures"
TODAY = date(2026, 11, 23)
# outlet id, the month scanned, then what its recorded files give: how many URLs, the first and
# the last (see each outlet's sources.json and fixtures/README.md).
RECORDED: list[tuple[str, Month, int, str, str]] = [
    (
        "a-haber",
        Month(2023, 2),
        20,
        "https://www.ahaber.com.tr/yasam/2025/10/02/dogal-afetlerden-koruyan-dua-zilzal-suresinin-turkce-arapca-okunusu-deprem-aninda-okunur-mu",
        "https://www.ahaber.com.tr/gundem/2023/01/31/altili-masada-yeni-kaos-ahmet-davutoglundan-ortaklarina-yaylim-atesi-icazet-almadan-konusanlar-lutfen-susun",
    ),
    (
        "aydinlik",
        Month(2023, 2),
        20,
        "https://www.aydinlik.com.tr/haber/unsal-ban-ve-ailesi-hakkinda-tutuklama-karari-367827",
        "https://www.aydinlik.com.tr/haber/istiklal-ve-yeni-emperyalizmin-cikis-yollari-364719",
    ),
    (
        "bloomberg-ht",
        Month(2023, 2),
        36,
        "https://www.bloomberght.com/resmi-gazete-de-bugun-01022023-2324380",
        "https://www.bloomberght.com/musk-chatgpt-ye-rakip-olmaya-hazirlaniyor-2326069",
    ),
    (
        "diken",
        Month(2023, 2),
        88,
        "https://www.diken.com.tr/bakanlik-destekliyor-muslum-gursesin-felsefesi-z-kusagi-ile-bulusacak/",
        "https://www.diken.com.tr/iyi-partide-rahatsizlik-haberler-nereden-cikti-anlamadik/",
    ),
    (
        "evrensel",
        Month(2023, 2),
        26,
        "https://www.evrensel.net/haber/480910/ozgur-gundem-nobetci-yayin-yonetmenligi-davasi-25-mayisa-ertelendi",
        "https://www.evrensel.net/haber/483656/izmir-korfezinde-4-1-buyuklugunde-deprem-meydana-geldi",
    ),
    (
        "haber-global",
        Month(2023, 2),
        40,
        "https://haberglobal.com/spor/vinicius-juniora-irkci-hakaretlerde-bulunan-taraftara-para-ve-tribunlerden-men-cezasi-234945",
        "https://haberglobal.com/gundem/tekirdagda-supheli-aractan-uyusturucu-cikti-228870",
    ),
    (
        "haberturk",
        Month(2023, 2),
        13,
        "https://www.haberturk.com/3-super-lig-hakemi-uefa-nin-core-kursuna-katildi-3569757-spor",
        "https://www.haberturk.com/humeze-suresi-okunusu-ve-anlami-humeze-suresi-arapca-yazilisi-turkce-anlami-meali-tefsiri-ve-okunusu-3564503",
    ),
    (
        "kisa-dalga",
        Month(2023, 2),
        26,
        "https://kisadalga.net/haber/detay/avrupa-birliginin-schengen-vizesine-dijital-basvuru-donemi_54785",
        "https://kisadalga.net/haber/detay/bahceli-dertlerini-anlatmak-isteyen-depremzedeleri-boyle-azarladi-sessizlik-olacak-dagilin-gidin_58837",
    ),
    (
        "mynet",
        Month(2023, 2),
        60,
        "https://www.mynet.com/tok-zit-anlamlisi-nedir-tokun-zit-anlamlisi-kelime-ve-cumle-icinde-ornek-kullanim-170100287402",
        "https://www.mynet.com/haber/oruc-ne-zaman-basliyor-ve-bitiyor-2023-ramazan-ayi-ne-zaman-baslayacak-iste-ilk-sahur-tarihi-110107101340",
    ),
    (
        "ntv",
        Month(2023, 2),
        152,
        "https://www.ntv.com.tr/sporskor/son-dakika-galatasarayda-seferovicle-yollar-ayrildi,xkSCsJzRb0SdYhlVZkZjsg",
        "https://www.ntv.com.tr/otomobil/tesla-meksikada-fabrika-kuracak,u5GRzYew6UWZIWnRKXQyZQ",
    ),
    (
        "odatv",
        Month(2023, 2),
        60,
        "https://www.odatv.com/guncel/yalanlari-ve-gercekleriyle-28-subat-272623",
        "https://www.odatv.com/dunya/fransada-isyan-yayiliyor-269118",
    ),
    (
        "olay",
        Month(2023, 2),
        101,
        "https://www.olay.com.tr/bursada-2-katli-ev-alev-alev-yandi-1094653",
        "https://www.olay.com.tr/bursadaki-trafik-kazasinda-2-kisi-yaralandi-2-1108070",
    ),
    (
        "ozgur-kocaeli",
        Month(2023, 2),
        20,
        "https://www.ozgurkocaeli.com.tr/haber/14109231/hodri-meydan-firsatcilara-firsat-vermeyecegiz",
        "https://www.ozgurkocaeli.com.tr/makale/13935027/adem-turgut/buyuksehir-geregini-yapti-minibuscu-de-geregini-yapsin",
    ),
    (
        "sabah",
        Month(2023, 2),
        40,
        "https://www.sabah.com.tr/fotohaber/yasam/yusuf-suresi-okunusu-yusuf-suresi-meali-turkce-anlami-arapca-yazilisi-ve-tefsiri-d1",
        "https://www.sabah.com.tr/spor/basketbol/2023/01/31/fenerbahce-beko-olympiakosa-kaybetti",
    ),
    (
        "sputnik-tr",
        Month(2023, 2),
        20,
        "https://anlatilaninotesi.com.tr/20230228/rus-mahkemesinden-wikipediaya-2-milyon-ruble-ceza-1067625459.html",
        "https://anlatilaninotesi.com.tr/20230201/isvec-basbakani-kristersson-duzenlenen-eylemlerin-guvenligi-karmasik-hale-getirdigini-soyledi-1066419906.html",
    ),
    (
        "takvim",
        Month(2023, 2),
        20,
        "https://www.takvim.com.tr/galeri/yasam/deprem-duasi-turkce-arapca-okunusu-ve-anlami-deprem-aninda-okunacak-dua-zilzal-zelzele-suresi-meali-dogal-afetlerden-korunma-duasi",
        "https://www.takvim.com.tr/guncel/2023/01/31/turkiye-ve-islam-karsiti-provokasyonlarin-merkezi-haline-gelen-isvecte-nato-panigi-buyuk-riskler",
    ),
    (
        "timeturk",
        Month(2023, 2),
        57,
        "https://www.timeturk.com/spor/alpaslan-ozturk-eyupspor-da-kadro-disi-mi-kaldi/haber-1759979",
        "https://www.timeturk.com/ekonomi/taksitle-telefon-alma-firsati/haber-1762363",
    ),
    (
        "turkgun",
        Month(2023, 2),
        20,
        "https://www.turkgun.com/yasam/dilenen-kadinin-kucagindaki-kundaktan-cikan-soke-etti/200074",
        "https://www.turkgun.com/dunya/bir-doneme-damgasini-vuran-oyuncu-hayatini-kaybetti/197769",
    ),
    (
        "yeni-asir",
        Month(2023, 2),
        20,
        "https://www.yeniasir.com.tr/gundem/2023/02/27/kamyonet-bariyere-carpti-iki-kisi-hayatini-kaybetti",
        "https://www.yeniasir.com.tr/ege/denizli/2023/02/01/denizlide-yksye-girecek-genclere-mujde",
    ),
]
IDS = [case[0] for case in RECORDED]


def sources(outlet_id: str) -> dict[str, str]:
    """Each recorded file of an outlet, by the URL it came from."""
    listing = json.loads((FIXTURES / outlet_id / "sources.json").read_text(encoding="utf-8"))
    return {url: name for name, url in listing.items()}


def serve(requests_mock: Mocker, outlet_id: str) -> None:
    outlet = get(outlet_id)
    for host in outlet.hosts:
        requests_mock.get(f"https://{host}/robots.txt", status_code=404)
    for url, name in sources(outlet_id).items():
        requests_mock.get(url, content=(FIXTURES / outlet_id / name).read_bytes())


@pytest.mark.parametrize(("outlet_id", "month", "count", "first", "last"), RECORDED, ids=IDS)
def test_each_new_outlet_reads_its_recorded_month(
    http: Http,
    requests_mock: Mocker,
    outlet_id: str,
    month: Month,
    count: int,
    first: str,
    last: str,
) -> None:
    serve(requests_mock, outlet_id)
    outlet = get(outlet_id)
    found = scan(outlet, http, month.start, month.next().start, today=TODAY)
    candidates = list(found)
    assert len(candidates) == count
    assert (candidates[0].url, candidates[-1].url) == (first, last)
    assert all(outlet.accepts(c.url) and c.url == c.url.strip() for c in candidates)
    assert {c.month for c in candidates} == {month}
    assert (found.gaps, found.dropped) == ([], 0)
    requested = [r.url for r in requests_mock.request_history if not r.url.endswith("robots.txt")]
    assert len(requested) == len(set(requested)), "a file was requested twice"


@pytest.mark.parametrize("outlet_id", IDS)
def test_each_new_outlet_is_built_in_and_explains_its_coverage(outlet_id: str) -> None:
    outlet = get(outlet_id)
    assert outlet.notes
    assert outlet.method in {"monthly sitemap", "chunked sitemap"}
    assert isinstance(outlet, (MonthlySitemap, ChunkedSitemap))
    assert outlet.earliest is not None
    assert (outlet in builtin()) is (outlet_id != "sputnik-tr")


FEB = Month(2023, 2)
SITEMAP = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


def recorded_urls(outlet_id: str, name: str) -> list[str]:
    root = parse_xml((FIXTURES / outlet_id / name).read_bytes(), max_bytes=10**8, url="https://x/")
    return [(entry.findtext(f"{SITEMAP}loc") or "").strip() for entry in root]


def archive_requests(requests_mock: Mocker) -> list[str]:
    return [r.url for r in requests_mock.request_history if not r.url.endswith("robots.txt")]


def month_files(outlet_id: str) -> list[tuple[str, str]]:
    """An outlet's recorded files for February 2023, as (name, source URL), in index order."""
    listing = json.loads((FIXTURES / outlet_id / "sources.json").read_text(encoding="utf-8"))
    return [(name, url) for name, url in listing.items() if name.startswith("2023-02")]


def test_sabahs_parts_give_every_url_once_in_index_order(http: Http, requests_mock: Mocker) -> None:
    serve(requests_mock, "sabah")
    found = scan(get("sabah"), http, FEB.start, FEB.next().start, today=TODAY)
    candidates = list(found)
    files = month_files("sabah")
    assert len(files) == 2
    expected = list(dict.fromkeys(u for name, _ in files for u in recorded_urls("sabah", name)))
    assert [c.url for c in candidates] == expected
    assert list(dict.fromkeys(c.source for c in candidates)) == [url for _, url in files]
    assert (found.months, found.gaps) == ([FEB], [])


def test_a_sabah_part_that_fails_is_a_gap_naming_it(http: Http, requests_mock: Mocker) -> None:
    serve(requests_mock, "sabah")
    (first_name, first_url), (_, second_url) = month_files("sabah")
    requests_mock.get(second_url, status_code=404)
    found = scan(get("sabah"), http, FEB.start, FEB.next().start, today=TODAY)
    candidates = list(found)
    assert [c.url for c in candidates] == recorded_urls("sabah", first_name)
    assert {c.source for c in candidates} == {first_url}
    [gap] = found.gaps
    assert (gap.reason, gap.month, gap.url) == ("failed", FEB, second_url)
    assert gap.detail.startswith("file 2 of 2 for 2023-02 couldn't be read")
    assert found.months == []


def test_haberturks_february_takes_marchs_articles_in_its_span_and_nothing_else(
    http: Http, requests_mock: Mocker
) -> None:
    serve(requests_mock, "haberturk")
    outlet = get("haberturk")
    assert isinstance(outlet, MonthlySitemap)
    found = scan(outlet, http, FEB.start, FEB.next().start, today=TODAY)
    candidates = list(found)
    jan, feb, mar = (recorded_urls("haberturk", f"2023-0{m}.xml") for m in (1, 2, 3))

    def number(url: str) -> int | None:
        return article_id(outlet, url)

    low = max(n for u in jan if (n := number(u)) is not None)
    high = max(n for u in feb if (n := number(u)) is not None)
    own = [u for u in feb if (n := number(u)) is None or n > low]
    ahead = [u for u in mar if (n := number(u)) is not None and low < n <= high]
    assert [c.url for c in candidates] == own + ahead
    # The recorded files hold each case: old articles edited in February, which stay out;
    # February's articles edited in March, which come in; and March's own, which stay out.
    later = [u for u in mar if (n := number(u)) is not None and n > high]
    assert len(own) < len(feb)
    assert ahead
    assert later
    assert {c.month for c in candidates} == {FEB}
    requested = archive_requests(requests_mock)
    assert sorted(requested) == sorted({*requested})
    assert len(requested) == 4


def test_odatvs_entries_come_with_headlines_and_days_and_search_keeps_their_days(
    http: Http, requests_mock: Mocker
) -> None:
    serve(requests_mock, "odatv")
    found = scan(get("odatv"), http, FEB.start, FEB.next().start, today=TODAY)
    candidates = list(found)
    assert candidates
    assert all(c.title and c.day for c in candidates)
    start, end = date(2023, 2, 10), date(2023, 2, 20)
    query = KeywordQuery(["deprem"])
    matching = [c for c in candidates if query.match(title=c.title, url=c.url)]
    inside = [c for c in matching if c.day is not None and start <= c.day < end]
    run = OutletRun(get("odatv"))
    collect(run, candidates, query, start, end)
    assert [row.url for row in run.rows] == [clean_url(c.url) for c in inside]
    assert run.trimmed == len(matching) - len(inside)
    assert inside
    assert run.trimmed
