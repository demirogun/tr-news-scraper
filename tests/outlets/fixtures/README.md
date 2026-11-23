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
