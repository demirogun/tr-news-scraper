"""The outlets 1.1 adds, read from archive files recorded on 2026-11-23 (SPEC-1.1 P4)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from requests_mock import Mocker

from tr_news_scraper._http import Http
from tr_news_scraper.outlets import ChunkedSitemap, Month, MonthlySitemap, builtin, get
from tr_news_scraper.outlets._scan import scan

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
