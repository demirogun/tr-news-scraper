# Article page skeletons

One page per built-in outlet, made with `scripts/make_page_fixtures.py` from pages read on
2026-11-08 with tr-news-scraper's own client: robots.txt obeyed, honest User-Agent, one request per
second per site.

A skeleton keeps the page's structure, headline, dates and metadata, so fetch's tests exercise each
outlet's real markup. It doesn't keep the article:
- **Replaced with filler of the same length:**
  - every text in a paragraph, list item, caption, quote, table cell or subheading;
  - every other body text of three or more words;
  - every description;
  - every JSON-LD `articleBody` or `description`.

  Texts of eight or more words include "deprem". Dates, times, and text inside elements named
  for times, dates, authors or sources stay.
- **Fictional names:** journalists' bylines became fictional names, wherever they appeared. Desk
  and agency names ("Haber Merkezi", "IHA") stay.
- **Removed:** scripts other than JSON-LD, styles, iframes, SVG, comments and noscript blocks.
  Only the canonical link stays, and every page declares UTF-8.

No file here contains article text or a real journalist's name.

| File | Source | Byline |
|---|---|---|
| `aksam/page.html` | https://www.aksam.com.tr/cumartesi/cocuklara-deprem-nasil-anlatilir/haber-1345913 | fictional |
| `cumhuriyet/page.html` | https://www.cumhuriyet.com.tr/bilim-teknoloji/abdli-uzay-sirketi-depremin-uydu-goruntulerini-yayinladi-2049504 | desk |
| `euronews-tr/page.html` | https://tr.euronews.com/2023/02/28/kahramanmaras-depremleri-sonrasi-suriyede-22-kisi-kolera-nedeniyle-hayatini-kaybetti | none |
| `milliyet/page.html` | https://www.milliyet.com.tr/galeri/son-depremler-listesi-7-kasim-az-once-deprem-mi-oldu-nerede-kac-siddetinde-afad-kandilli-deprem-sorgulama-7695901 | fictional |
| `sozcu/page.html` | https://www.sozcu.com.tr/hatay-da-4-1-buyuklugunde-deprem-p55330 | desk |
| `star/page.html` | https://www.star.com.tr/yasam/vatandaslar-gozlerine-inanamadi-depremin-ardindan-camura-bulandi-haber-1767589/ | agency |
| `trt-haber/page.html` | https://www.trthaber.com/haber/bilim-teknoloji/deprem-felaketinden-sonra-dijital-ikiz-teknolojisi-hizla-yayginlasiyor-750285.html | fictional |

To rebuild one, save the page as UTF-8 text and run, with one `--author` for every spelling of the
byline, its URL slug and any username:

```bash
uv run python scripts/make_page_fixtures.py page.html tests/fetch/fixtures/<outlet>/page.html \
    --author "Real Name=Fictional Name"
```
