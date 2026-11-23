# Recorded archive files

These are trimmed copies of real responses, fetched on 2026-11-07 with tr-news-scraper's own client:
robots.txt obeyed, honest User-Agent, one request per second per site.

- Each index keeps its two newest and two oldest months, plus the months the tests use. Sözcü's
  index also keeps its entries that aren't month files.
- Each month file keeps 20 entries: the first 8, the last 8, and up to 4 entries in between whose
  URL contains "deprem". Video elements were removed.
- Milliyet's search pages keep their first 5 results, and each result's summary is replaced with
  "…". Page 401 is the empty page that follows the last results.
- Nothing here contains article text. The files hold URLs, dates, headlines, and image titles
  (headlines for Star, photo titles for Euronews Türkçe).

| File | Source |
|---|---|
| `cumhuriyet/index.xml` | https://www.cumhuriyet.com.tr/sitemaps/posts.xml |
| `cumhuriyet/2023-02.xml` | https://www.cumhuriyet.com.tr/sitemaps/posts-2023-2.xml |
| `euronews-tr/index.xml` | https://tr.euronews.com/sitemap/articles.xml |
| `euronews-tr/2023-02.xml` | https://tr.euronews.com/sitemap/articles-2023-02.xml |
| `trt-haber/index.xml` | https://www.trthaber.com/sitemaps/news.xml |
| `trt-haber/2023-02.xml` | https://www.trthaber.com/sitemaps/news-2023-02.xml |
| `star/index.xml` | https://www.star.com.tr/sitemaps/posts.xml |
| `star/2023-02.xml` | https://www.star.com.tr/sitemaps/posts-2023-02.xml |
| `aksam/index.xml` | https://www.aksam.com.tr/sitemaps/posts.xml |
| `aksam/2023-02.xml` | https://www.aksam.com.tr/sitemaps/posts-2023-02.xml |
| `sozcu/index.xml` | https://www.sozcu.com.tr/feeds/sitemapindex |
| `sozcu/2024-06.xml` | https://www.sozcu.com.tr/feeds/sitemapposts?year=2024&month=6 |
| `milliyet/deprem-page-1.html` | https://www.milliyet.com.tr/api/search/searchcontentloadmore?query=deprem&page=1 |
| `milliyet/deprem-page-400.html` | the same search, `page=400` |
| `milliyet/deprem-page-401.html` | the same search, `page=401` |

## Recorded on 2026-11-23, for the outlets 1.1 adds

Fetched the same way, through tr-news-scraper's own client. Each outlet's `sources.json`
maps its files to the URLs they came from, and the tests serve them there.

- An index keeps its two oldest and two newest months (their first file) and the files the
  tests read; a chunked archive's index keeps its oldest and newest files and the files
  around February 2023. Entries that aren't month or numbered files stay.
- A month file keeps 20 entries, as above; a month with several files keeps its first three,
  in index order. Habertürk's January, February and March keep the entries that exercise
  its article-number span.
- A numbered file keeps its first and last 5 entries and up to 30 entries dated within three
  days of February 2023, spread evenly.
- No entry whose URL names an author (`/yazar/`, `/yazarlar/`, `/author/` ...) is kept.

| File | Source |
|---|---|
| `a-haber/index.xml` | https://www.ahaber.com.tr/sitemap/post.xml |
| `a-haber/2023-02.xml` | https://www.ahaber.com.tr/sitemaparchives/post/2023-2.xml |
| `aydinlik/index.xml` | https://www.aydinlik.com.tr/sitemap/index |
| `aydinlik/2023-02.xml` | https://www.aydinlik.com.tr/sitemap/2023/2 |
| `bloomberg-ht/index.xml` | https://www.bloomberght.com/sitemap.xml |
| `bloomberg-ht/chunk-0001.xml` | https://www.bloomberght.com/sitemap_news_0.xml |
| `bloomberg-ht/chunk-0184.xml` | https://www.bloomberght.com/sitemap_news_183.xml |
| `bloomberg-ht/chunk-0185.xml` | https://www.bloomberght.com/sitemap_news_184.xml |
| `bloomberg-ht/chunk-0186.xml` | https://www.bloomberght.com/sitemap_news_185.xml |
| `bloomberg-ht/chunk-0231.xml` | https://www.bloomberght.com/sitemap_news_230.xml |
| `diken/index.xml` | https://www.diken.com.tr/sitemap.xml |
| `diken/chunk-0001.xml` | https://www.diken.com.tr/post-sitemap256.xml |
| `diken/chunk-0177.xml` | https://www.diken.com.tr/post-sitemap80.xml |
| `diken/chunk-0178.xml` | https://www.diken.com.tr/post-sitemap79.xml |
| `diken/chunk-0179.xml` | https://www.diken.com.tr/post-sitemap78.xml |
| `diken/chunk-0180.xml` | https://www.diken.com.tr/post-sitemap77.xml |
| `diken/chunk-0256.xml` | https://www.diken.com.tr/post-sitemap.xml |
| `evrensel/index.xml` | https://www.evrensel.net/sitemap.xml |
| `evrensel/chunk-0001.xml` | https://www.evrensel.net/sitemap/haber/1.xml |
| `evrensel/chunk-0046.xml` | https://www.evrensel.net/sitemap/haber/46.xml |
| `evrensel/chunk-0047.xml` | https://www.evrensel.net/sitemap/haber/47.xml |
| `evrensel/chunk-0062.xml` | https://www.evrensel.net/sitemap/haber/62.xml |
| `haber-global/index.xml` | https://haberglobal.com/sitemap.xml |
| `haber-global/2023-02-1.xml` | https://haberglobal.com/sitemap-articles-2023-02.xml |
| `haber-global/2023-02-2.xml` | https://haberglobal.com/sitemap-articles-2023-02-2.xml |
| `haberturk/index.xml` | https://www.haberturk.com/sitemap_posts.xml |
| `haberturk/2023-01.xml` | https://www.haberturk.com/sitemap_post_202301.xml |
| `haberturk/2023-02.xml` | https://www.haberturk.com/sitemap_post_202302.xml |
| `haberturk/2023-03.xml` | https://www.haberturk.com/sitemap_post_202303.xml |
| `kisa-dalga/index.xml` | https://kisadalga.net/sitemap.xsd |
| `kisa-dalga/chunk-0001.xml` | https://kisadalga.net/sitemap-news-01.xml |
| `kisa-dalga/chunk-0002.xml` | https://kisadalga.net/sitemap-news-02.xml |
| `kisa-dalga/chunk-0004.xml` | https://kisadalga.net/sitemap-news-04.xml |
| `mynet/index.xml` | https://www.mynet.com/sitemaps/all-index.xml |
| `mynet/2023-02-1.xml` | https://www.mynet.com/sitemaps/monthly/egitim/2023-02.xml |
| `mynet/2023-02-2.xml` | https://www.mynet.com/sitemaps/monthly/finans/2023-02.xml |
| `mynet/2023-02-3.xml` | https://www.mynet.com/sitemaps/monthly/haber/2023-02.xml |
| `ntv/index.xml` | https://www.ntv.com.tr/story-sitemap |
| `ntv/chunk-0001.xml` | https://www.ntv.com.tr/story-sitemap/1 |
| `ntv/chunk-0643.xml` | https://www.ntv.com.tr/story-sitemap/643 |
| `ntv/chunk-0644.xml` | https://www.ntv.com.tr/story-sitemap/644 |
| `ntv/chunk-0645.xml` | https://www.ntv.com.tr/story-sitemap/645 |
| `ntv/chunk-0646.xml` | https://www.ntv.com.tr/story-sitemap/646 |
| `ntv/chunk-0647.xml` | https://www.ntv.com.tr/story-sitemap/647 |
| `ntv/chunk-0648.xml` | https://www.ntv.com.tr/story-sitemap/648 |
| `ntv/chunk-0952.xml` | https://www.ntv.com.tr/story-sitemap/952 |
| `odatv/index.xml` | https://www.odatv.com/categories.xml |
| `odatv/2023-02-1.xml` | https://www.odatv.com/guncel/2023-02.xml |
| `odatv/2023-02-2.xml` | https://www.odatv.com/ekonomi/2023-02.xml |
| `odatv/2023-02-3.xml` | https://www.odatv.com/dunya/2023-02.xml |
| `olay/index.xml` | https://www.olay.com.tr/sitemap_index.xml |
| `olay/chunk-0001.xml` | https://www.olay.com.tr/post-sitemap433.xml |
| `olay/chunk-0323.xml` | https://www.olay.com.tr/post-sitemap111.xml |
| `olay/chunk-0324.xml` | https://www.olay.com.tr/post-sitemap110.xml |
| `olay/chunk-0325.xml` | https://www.olay.com.tr/post-sitemap109.xml |
| `olay/chunk-0326.xml` | https://www.olay.com.tr/post-sitemap108.xml |
| `olay/chunk-0327.xml` | https://www.olay.com.tr/post-sitemap107.xml |
| `olay/chunk-0433.xml` | https://www.olay.com.tr/post-sitemap1.xml |
| `ozgur-kocaeli/index.xml` | https://www.ozgurkocaeli.com.tr/sitemap.xml |
| `ozgur-kocaeli/2023-02.xml` | https://www.ozgurkocaeli.com.tr/sites/535/sitemaps/sitemap-2023-02.xml |
| `sabah/index.xml` | https://www.sabah.com.tr/sitemap/post.xml |
| `sabah/2023-02-1.xml` | https://www.sabah.com.tr/sitemaparchives/post/2023-2-1.xml |
| `sabah/2023-02-2.xml` | https://www.sabah.com.tr/sitemaparchives/post/2023-2.xml |
| `sputnik-tr/index.xml` | https://anlatilaninotesi.com.tr/sitemap_article_index.xml |
| `sputnik-tr/2023-02.xml` | https://anlatilaninotesi.com.tr/sitemap_article.xml?date_start=20230201&date_end=20230228 |
| `takvim/index.xml` | https://www.takvim.com.tr/sitemap/post.xml |
| `takvim/2023-02.xml` | https://www.takvim.com.tr/sitemaparchives/post/2023-2.xml |
| `timeturk/index.xml` | https://www.timeturk.com/sitemap.xml |
| `timeturk/chunk-0001.xml` | https://www.timeturk.com/sitemap-posts-373.xml |
| `timeturk/chunk-0292.xml` | https://www.timeturk.com/sitemap-posts-82.xml |
| `timeturk/chunk-0293.xml` | https://www.timeturk.com/sitemap-posts-81.xml |
| `timeturk/chunk-0294.xml` | https://www.timeturk.com/sitemap-posts-80.xml |
| `timeturk/chunk-0295.xml` | https://www.timeturk.com/sitemap-posts-79.xml |
| `timeturk/chunk-0373.xml` | https://www.timeturk.com/sitemap-posts-1.xml |
| `turkgun/index.xml` | https://www.turkgun.com/sitemap.xml |
| `turkgun/2023-02.xml` | https://www.turkgun.com/sitemap/news-2023-02.xml |
| `yeni-asir/index.xml` | https://www.yeniasir.com.tr/sitemap/post.xml |
| `yeni-asir/2023-02.xml` | https://www.yeniasir.com.tr/sitemaparchives/post/2023-2.xml |
