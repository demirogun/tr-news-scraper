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
