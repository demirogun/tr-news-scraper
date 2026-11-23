"""Live check (weekly CI only): robots.txt still allows what tr-news-scraper reads, and still
forbids what it must not.

Run with ``uv run pytest -m live tests/live --no-cov``. These tests talk to real news sites, with
robots.txt obeyed and the honest User-Agent, so they never run in the normal test suite. A failure
means an outlet changed its rules: the outlet has to change too.
"""

from __future__ import annotations

from urllib.parse import urlsplit

import pytest

from tests.live.networks import ON_GITHUB, hosts_refusing_github
from tr_news_scraper._http import Http

# URLs that tr-news-scraper reads, one per 1.0 outlet still built in (checked 2026-11-07) and an
# archive file and an article per host 1.1 adds (checked 2026-11-23); each site's robots.txt
# allows them.
ALLOWED = {
    "Cumhuriyet": "https://www.cumhuriyet.com.tr/sitemaps/posts-2023-2.xml",
    "Euronews Türkçe": "https://tr.euronews.com/sitemap/articles-2023-02.xml",
    "TRT Haber": "https://www.trthaber.com/sitemaps/news-2023-02.xml",
    "Star": "https://www.star.com.tr/sitemaps/posts-2023-02.xml",
    "Akşam": "https://www.aksam.com.tr/sitemaps/posts-2023-02.xml",
    "Sözcü": "https://www.sozcu.com.tr/feeds/sitemapposts?year=2024&month=6",
    "A Haber archive": "https://www.ahaber.com.tr/sitemaparchives/post/2023-2.xml",
    "A Haber article": (
        "https://www.ahaber.com.tr/yasam/2025/10/02/dogal-afetlerden-koruyan-dua-zilzal-suresinin-turkce-arapca-okunusu-deprem-aninda-okunur-mu"
    ),
    "Aydınlık archive": "https://www.aydinlik.com.tr/sitemap/2023/2",
    "Aydınlık article": (
        "https://www.aydinlik.com.tr/fotogaleri/hosgoru-kentinde-ezan-ve-can-sesinin-birbirine-karistigi-yapilar-depremden-zarar-gordu-hatay-haberleri-depremde-zarar-goren-kiliselercamiler-kultur-mirasi-368527"
    ),
    "Bloomberg HT archive": "https://www.bloomberght.com/sitemap_news_0.xml",
    "Bloomberg HT article": (
        "https://www.bloomberght.com/afet-bolgesinde-deprem-suclari-sorusturma-burolari-kurulacak-2325149"
    ),
    "Diken archive": "https://www.diken.com.tr/post-sitemap256.xml",
    "Diken article": (
        "https://www.diken.com.tr/simdi-reklamlar-bakan-koca-deprem-bolgesinde-propaganda-filmi-cekti/"
    ),
    "Evrensel archive": "https://www.evrensel.net/sitemap/haber/1.xml",
    "Evrensel article": (
        "https://www.evrensel.net/haber/481019/afadin-duzce-depreminde-sinifta-kaldigi-ortaya-cikti"
    ),
    "Haber Global archive": "https://haberglobal.com/sitemap-articles-2023-02.xml",
    "Haber Global article": (
        "https://haberglobal.com/dunya/suriyede-depremde-can-kaybi-5-bin-814e-yukseldi-232069"
    ),
    "Habertürk archive": "https://www.haberturk.com/sitemap_post_202301.xml",
    "Habertürk article": (
        "https://www.haberturk.com/turkiye-diri-fay-haritalari-mta-yenilenmis-mta-diri-fay-hatti-haritasi-fay-hatti-gecen-deprem-riskli-bolgeler-iller-ve-ilceler-listesi-3569010"
    ),
    "Kısa Dalga archive": "https://kisadalga.net/sitemap-news-01.xml",
    "Kısa Dalga article": (
        "https://kisadalga.net/haber/detay/naci-gorurden-rahatlatan-deprem-aciklamasi-zamanla-azalacak_58844"
    ),
    "Mynet archive": "https://www.mynet.com/sitemaps/monthly/egitim/2023-02.xml",
    "Mynet article": (
        "https://www.mynet.com/deprem-cantasina-konulmasi-gereken-yiyecekler-cantanizi-onceden-ayarlayin-1219718-myyemek"
    ),
    "NTV archive": "https://www.ntv.com.tr/story-sitemap/1",
    "NTV article": (
        "https://www.ntv.com.tr/turkiye/galeri-deprem-bolgesinde-hangi-ilde-kac-cadir-kuruldu,RHVWIEpipUG1zJcIg3-07A"
    ),
    "Odatv archive": "https://www.odatv.com/guncel/2023-02.xml",
    "Odatv article": (
        "https://www.odatv.com/guncel/sadat-kurucusundan-deprem-cikisi-suruden-ayrilmayin-diye-ilahi-ikaz-272069"
    ),
    "Olay archive": "https://www.olay.com.tr/post-sitemap433.xml",
    "Olay article": (
        "https://www.olay.com.tr/cevad-prekazi-formasinin-gelirini-depremzedelere-bagisladi-1101348"
    ),
    "Özgür Kocaeli archive": (
        "https://www.ozgurkocaeli.com.tr/sites/535/sitemaps/sitemap-2023-02.xml"
    ),
    "Özgür Kocaeli article": (
        "https://www.ozgurkocaeli.com.tr/haber/13963045/kahramanmarasta-77-buyuklugunde-deprem"
    ),
    "Sabah archive": "https://www.sabah.com.tr/sitemaparchives/post/2023-2-1.xml",
    "Sabah article": (
        "https://www.sabah.com.tr/galeri/yasam/son-dakika-konyada-deprem-mi-oldu-kac-siddetinde-afad-ve-kandilli-ile-konyada-deprem-bekleniyor-mu"
    ),
    "Sputnik Türkiye archive": (
        "https://anlatilaninotesi.com.tr/sitemap_article.xml?date_start=20230201&date_end=20230228"
    ),
    "Sputnik Türkiye article": (
        "https://anlatilaninotesi.com.tr/20230202/iran-azerbaycanin-depremzedeler-icin-yardimini-kabul-etmedi-1066487967.html"
    ),
    "Takvim archive": "https://www.takvim.com.tr/sitemaparchives/post/2023-2.xml",
    "Takvim article": (
        "https://www.takvim.com.tr/yasam/2023/02/03/son-dakika-deprem-osmaniyede-46-buyuklugunde-deprem-son-depremler"
    ),
    "Timeturk archive": "https://www.timeturk.com/sitemap-posts-373.xml",
    "Timeturk article": (
        "https://www.timeturk.com/gundem/ingiliz-uzmandan-dikkat-ceken-analiz-deprem-mi-yoksa-bir-tur-teror-eylemi-mi/haber-1761529"
    ),
    "Türkgün archive": "https://www.turkgun.com/sitemap/news-2023-02.xml",
    "Türkgün article": (
        "https://www.turkgun.com/gundem/sosyal-medyadan-depremle-ilgili-provokatif-paylasim-yapan-ercan-hakkinda-flas-karar/200081"
    ),
    "Yeni Asır archive": "https://www.yeniasir.com.tr/sitemaparchives/post/2023-2.xml",
    "Yeni Asır article": (
        "https://www.yeniasir.com.tr/gundem/2023/02/28/deprem-firtinasi-suruyor-kayseri-ikinci-kez-sallandi"
    ),
    "Sabah (finans.sabah.com.tr) article": (
        "https://finans.sabah.com.tr/ekonomi/abdde-mal-ticareti-acigi-ocakta-yuzde-2-artti-6376813"
    ),
    "Mynet (finans.mynet.com) article": (
        "https://finans.mynet.com/haber/detay/ekonomi/a101-de-9-taksitle-109-bin-tl-ye-tekne-satilacak-iste-2-subat-aldin-aldin-katalogu/460067/"
    ),
}
# Endpoints that 0.1.0 or 1.0 used, or that we once planned to use, and that robots.txt now
# forbids.
DISALLOWED = {
    "Milliyet search (1.0's; disallowed since 2026-11-23)": (
        "https://www.milliyet.com.tr/api/search/searchcontentloadmore?query=deprem&page=1"
    ),
    "Sabah search": "https://www.sabah.com.tr/get/arama?query=deprem",
    "Hürriyet search": "https://www.hurriyet.com.tr/api/search/searchcontentloadmore?query=deprem",
    "CNN Türk tag list (disallowed since 2026-11-07)": (
        "https://www.cnnturk.com/api/lazy/loadmore?tags=deprem&skip=0&top=10"
    ),
}


@pytest.fixture(scope="module")
def http() -> Http:
    return Http()


@pytest.mark.live
@pytest.mark.parametrize("url", ALLOWED.values(), ids=ALLOWED.keys())
def test_robots_txt_allows_the_urls_we_read(http: Http, url: str) -> None:
    if unread_on_github(http, url):
        host = urlsplit(url).hostname
        pytest.skip(f"{host} refuses GitHub's runners its robots.txt (tests/live/networks.py)")
    assert http._robots.allows(url)


def unread_on_github(http: Http, url: str) -> bool:
    """Whether the URL's site refuses GitHub's runners and its robots.txt couldn't be read here.
    RFC 9309 then allows everything, so checking would prove nothing."""
    if not (ON_GITHUB and urlsplit(url).hostname in hosts_refusing_github()):
        return False
    rules = http._robots._rules_for(url)
    return rules.parser is None and rules.allow_all


@pytest.mark.live
@pytest.mark.parametrize("url", DISALLOWED.values(), ids=DISALLOWED.keys())
def test_endpoints_we_must_not_use_are_still_disallowed(http: Http, url: str) -> None:
    assert not http._robots.allows(url)
