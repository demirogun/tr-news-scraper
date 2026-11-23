# Article page skeletons

One page per built-in outlet, made with `scripts/make_page_fixtures.py` from pages read on
2026-11-08 with tr-news-scraper's own client: robots.txt obeyed, honest User-Agent, one request per
second per site. The seven were rebuilt on 2026-11-23 from the same saved pages, with the rules
below; nothing was downloaded again.

A skeleton keeps the page's structure, headline, dates and metadata, so fetch's tests exercise each
outlet's real markup. It doesn't keep the article:
- **Replaced with filler of the same length:**
  - every text in a paragraph, list item, caption, quote, table cell or subheading;
  - every other body text of three or more words;
  - every description;
  - every JSON-LD `articleBody` or `description`.

  Equal texts, and texts 98% alike, get the same filler, so a lead that repeats the page's
  description still does; any other text gets filler unlike every other's. Texts of eight or more
  words include "deprem". Dates, times, and text inside elements named for times, dates, authors or
  sources stay.
- **Fictional names:** every journalist named as an author, in JSON-LD, a meta tag or the page's
  byline, became a fictional name in every spelling: as written, in capitals, title case and
  lowercase, folded, as a URL slug, and as the usernames sites make of it. So did every other
  name in an element named for an author, or in a link to an author's page (such as the
  columnists a sidebar lists), and every author profile URL points at the fictional slug. Desk
  and agency names ("Haber Merkezi", "IHA") stay.
- **Removed:** scripts other than JSON-LD, styles, iframes, SVG, comments and noscript blocks.
  Only the canonical link stays, and every page declares UTF-8.

No file here contains article text or a real journalist's name. After the rebuild, every word of
each real byline (folded, longer than two letters) was searched for in its skeleton, and none was
found; nor was any name-like text in an author element or an author link that isn't fictional, a
desk or an agency. (Milliyet's skeleton, as first published in 1.0, still had the columnists of
its sidebar; it was rebuilt on 2026-11-23.)

| File | Source | Byline |
|---|---|---|
| `a-haber/page.html` | https://www.ahaber.com.tr/yasam/2025/10/02/dogal-afetlerden-koruyan-dua-zilzal-suresinin-turkce-arapca-okunusu-deprem-aninda-okunur-mu | desk |
| `aksam/page.html` | https://www.aksam.com.tr/cumartesi/cocuklara-deprem-nasil-anlatilir/haber-1345913 | fictional |
| `cumhuriyet/page.html` | https://www.cumhuriyet.com.tr/bilim-teknoloji/abdli-uzay-sirketi-depremin-uydu-goruntulerini-yayinladi-2049504 | desk |
| `euronews-tr/page.html` | https://tr.euronews.com/2023/02/28/kahramanmaras-depremleri-sonrasi-suriyede-22-kisi-kolera-nedeniyle-hayatini-kaybetti | none |
| `milliyet/page.html` | https://www.milliyet.com.tr/galeri/son-depremler-listesi-7-kasim-az-once-deprem-mi-oldu-nerede-kac-siddetinde-afad-kandilli-deprem-sorgulama-7695901 | fictional |
| `sozcu/page.html` | https://www.sozcu.com.tr/hatay-da-4-1-buyuklugunde-deprem-p55330 | desk |
| `star/page.html` | https://www.star.com.tr/yasam/vatandaslar-gozlerine-inanamadi-depremin-ardindan-camura-bulandi-haber-1767589/ | agency |
| `trt-haber/page.html` | https://www.trthaber.com/haber/bilim-teknoloji/deprem-felaketinden-sonra-dijital-ikiz-teknolojisi-hizla-yayginlasiyor-750285.html | fictional |

To rebuild one, save the page as UTF-8 text and run the script. Bylines named in JSON-LD or a
`meta[name=author]` tag get fictional names on their own; give `--author` for a byline that appears
only in the page's text, and to choose the fictional name:

```bash
uv run python scripts/make_page_fixtures.py page.html tests/fetch/fixtures/<outlet>/page.html \
    --author "Real Name=Fictional Name"
```

Then search the skeleton for every word of the real byline before committing it.
