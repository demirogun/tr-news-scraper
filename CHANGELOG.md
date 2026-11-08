# Changelog

All notable changes to tr-news-scraper are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

1.0 is a rewrite. It finds articles by keyword and date range in the archives of seven
Turkish-language outlets, using only what their robots.txt allows. It reads the articles' text
and reports what each outlet could and couldn't provide. Use it from Python (`search()`,
`fetch()`, `coverage()`) or with the new `trnews` command. It needs Python 3.12 or newer, and
[Migrating from 0.1.0](#migrating-from-010) explains what changed for 0.1.0's users.

### Added
- A polite network layer that every request goes through:
  - It identifies itself as `tr-news-scraper/<version> (+https://github.com/demirogun/tr-news-scraper)`.
    You can add a contact address, but you can't replace or disguise the User-Agent. Cookies are
    never stored or sent.
  - It checks each site's robots.txt (RFC 9309, wildcard rules included) before every request. An
    explicit `obey_robots=False` override exists; it logs a warning for every site it's used on.
  - It waits at least 1 second between requests to the same site, longer if robots.txt asks. It
    retries temporary failures up to three times, with growing waits or the server's `Retry-After`.
  - It caches successful responses in your user cache folder (at most 2 GiB), so a repeated search
    doesn't download everything again. An offline mode answers only from the cache.
- `tr_news_scraper.matching`, keyword matching that understands Turkish:
  - Correct Turkish casing (`IŞIK` → `ışık`, `İSTANBUL` → `istanbul`), and folding to match URL slugs
    (`Kahramanmaraş` → `kahramanmaras`).
  - A keyword of five or more letters matches words that start with it (`deprem` finds
    `depremzede`). A shorter one matches the word plus Turkish suffixes only (`sel` finds `sellerde`
    but not `selam`), including consonant changes (`obruk` → `obruğu`). `word*` forces prefix
    matching, and `"word"` forces an exact match.
  - It matches headlines, URL slugs and text, and every match comes with a reason. A URL that ends
    in a bare `haber-<id>` segment, as Akşam's do, is matched on the segment before it.
  - On 300 hand-labeled articles from Euronews Türkçe, TRT Haber and NTV, matching the URL and any
    real headline finds every article that names deprem, sel, heyelan, çığ or tsunami there, with
    precision ≥ 0.96. Some articles never name the hazard in their URL or headline (a landslide
    reported as "toprak kayması", an AFAD note ruling out a tsunami after an earthquake), so
    recall over all the articles about each hazard is 0.88–1.00.
  - Known limitations: names that look inflected match (`Selim` for `sel`), and so do metaphors
    ("Omicron tsunamisi"); synonyms aren't added, so search for landslides with both `heyelan`
    and `toprak kayma`; words that drop a vowel need their other form as a second keyword
    (`kayıp` → `kaybı`); and some outlets replace "ı" in URLs, so their URLs can miss words their
    headlines contain.

- `search()`, the new way to find news: keywords and a past date range in, one pandas table of
  articles out, with a report on every outlet.

  ```python
  from tr_news_scraper import search

  result = search(["deprem", "tsunami"], "2023-02-01", "2023-03-01")
  result.articles  # one row per article: outlet, month, day, title, url, matched, reasons, ...
  print(result)  # what each outlet found, and why some found nothing
  ```

  - An article is kept when its headline or URL names a keyword, and each row says why. A URL
    found twice, in two monthly files or for two keywords, is one row.
  - Every outlet is searched at the same time, and each site still gets one request per second.
    `deprem` in February 2023 returns 7,598 articles from five outlets.
  - Sitemap archives date an article only to its month, so until `fetch()` reads the page a row
    has its archive month; Milliyet's rows have their day. Entries last edited more than a day
    before the start can't be in the range: they're left out, and the report counts them.
  - The report gives each outlet's status (`ok`, `incomplete` or `failed`), how much of the range
    its archive covers, and why, such as "the archive starts in 2023-12". When every outlet fails,
    `SearchFailed` lists the reasons.
  - Ctrl+C stops every outlet before its next request, on Windows too.
  - The result records what was searched, when, and with which version.
- `fetch()`, which downloads the articles `search()` found and adds each one's text, author and
  publication time:

  ```python
  from tr_news_scraper import fetch, search

  fetched = fetch(search(["deprem"], "2023-02-01", "2023-03-01"))
  fetched.articles  # search's columns plus published, author, text, text_matched, copy_group, ...
  print(fetched)  # what each outlet read, and what failed
  ```

  - Text comes from trafilatura's general extractor, not per-site parsers, with its precision
    setting. On 33 test pages it kept weather widgets and share buttons out of the four texts
    they had crept into, and left the other 29 unchanged.
  - Search can date most archives only to the month, so `fetch()` settles the range from each
    page's original publication time. Articles published outside the range move to
    `fetched.outside` rather than disappearing.
  - Copies of one story, such as the same wire copy in several outlets, share a `copy_group`
    number: at least 80% of the shorter text's 8-word phrases, published at most 3 days apart.
    Nothing is removed, so counts can be corrected without losing anything.
  - Each outlet's pages are read one at a time, a second apart, and the outlets run together.
    Only what each page says is kept in your cache, not the page, so running the same call again
    continues where it stopped, even after Ctrl+C. `offline=True` reads only from the cache, and
    `refresh=True` downloads everything again.
  - An article that can't be read keeps the reason in its `error` column, such as "robots.txt
    disallows it". `FetchFailed` is raised only when no article could be read.
  - It also takes a DataFrame with `outlet` and `url` columns, such as a filtered
    `result.articles` or a table read back from a file, with `keywords=` to fill `text_matched`
    and an optional `progress` callback.
- `coverage()`, which lists what each outlet's archive covers without making a request.
  `coverage(check=True)` also checks every archive now, with two requests per outlet.
- `trnews`, a command line for the same search, for people who'd rather not write Python:

  ```bash
  trnews search deprem tsunami --from 2023-02-01 --to 2023-02-28 --fetch -o deprem.csv
  trnews fetch picked.csv -o picked-text.jsonl
  trnews coverage --check
  ```

  - `--to` is the last day, included. Every argument and output file is checked before the
    first request, and no file is replaced without `--overwrite`. A run's files are replaced
    together or not at all: if one is open in Excel, say, they all stay as they were.
  - Data goes to files, never to the terminal:
    - CSV in UTF-8 with a byte-order mark, so Excel shows Turkish letters. `--separator ";"`
      suits Excel with Turkish regional settings.
    - JSONL.
    - Parquet, with the new `[parquet]` extra: `pip install "tr-news-scraper[parquet]"`.

    Times are written in ISO 8601 with their offset.
  - Beside every table, `NAME.report.json` records:
    - what was searched, when, and with which version;
    - each outlet's report and every gap.

    It never records the `--contact` address. Rows whose page dates them outside the range go to
    `NAME.outside.EXT`.
  - `trnews fetch FILE` reads any table with `outlet` and `url` columns, such as a filtered search
    output. It takes the keywords and range from FILE's report file, so fetching in two steps
    gives the same rows as `--fetch`.
  - On a terminal, fetching shows one status line with each outlet's progress and the time left.
    Ctrl+C says how far it got; the articles read are already in the cache, so the same command
    continues.
  - Exit codes:
    - 0: done, even if nothing matched;
    - 1: nothing could be read, or a file couldn't be written;
    - 2: a usage mistake;
    - 130: stopped with Ctrl+C.
  - `python -m tr_news_scraper` runs the same command where the `trnews` script isn't on the PATH.
- `tr_news_scraper.outlets`, the news archives 1.0 reads, described as data you can extend:
  - Six built-in outlets publish monthly sitemaps that their robots.txt allows:
    - Cumhuriyet, from 1962 (every month since July 2008);
    - Euronews Türkçe, from 2010;
    - TRT Haber, from July 2016;
    - Star, from September 2012, with headlines;
    - Akşam, from December 2010;
    - Sözcü, from December 2023, when its new website started.
  - Milliyet is read through its site search, which robots.txt allows. Its results come with
    headlines and dates, but the search returns only its newest 10,000 results for each keyword.
    For "deprem" that reaches back to May 2024.
  - A past range in a search hundreds of pages deep is found with about ten requests (a binary
    search over the pages), not by reading every page.
  - Only the months an outlet's own sitemap index lists are ever requested. Anything that couldn't
    be read is reported with the reason: before the archive starts, past the end of a search,
    blocked by robots.txt, refused by the site, or failed.
  - You can add an outlet of your own by writing what it is, not code:
    `MonthlySitemap(id=..., name=..., index=..., month_file=...)`.
  - Milliyet articles that move to its `uzmanpara.milliyet.com.tr` section are followed; that
    host's robots.txt allows them.
  - Every week, GitHub Actions checks each built-in outlet against its real archive, and checks
    that its newest articles can still be read. When one breaks, the check opens an issue in this
    repository and closes it once the outlet works again.

### Changed
- Requires Python 3.12 or newer. Python 3.10 reached end of life in October 2026, and the exact
  pins in 0.1.0 could not be installed on Python 3.13 or newer.
- Packaging is a single `pyproject.toml` (hatchling build backend), and the package uses the `src/`
  layout.
- Dependencies are declared as version ranges instead of 31 exact pins, so security fixes reach you
  without a new tr-news-scraper release.
- tzdata is a new dependency. Archive times without an offset are read in Türkiye's time zone
  (Europe/Istanbul), including the UTC+2 winters before 2016, and Windows has no time zone
  database of its own.
- pandas stays a dependency, from version 2.2.3 (pandas 3 included). Importing tr_news_scraper
  doesn't import it: it loads when the first result table is built.
- trafilatura (2.3.1 or newer) replaces newspaper3k for reading article pages. It loads on the
  first extraction, and it only ever reads pages tr-news-scraper downloaded itself: its own
  downloader is never used. It raises the minimum lxml to 6.1.3 and urllib3 to 2.8.

### Removed
- `NewsScraper` and the `tr_news_scraper.tr_news_scraper` module. Importing it now raises an
  `ImportError` that points to [Migrating from 0.1.0](#migrating-from-010).
- newspaper3k, nltk, Pillow and the other pinned dependencies of 0.1.0.
- `setup.py` and `requirements.txt`.

### Security
- Dropped newspaper3k, nltk and Pillow. 0.1.0's 31 exact pins carried 108 known advisories (8
  critical), and Pillow's image decoders were reachable because newspaper3k downloads page images.
- CI audits every locked dependency with pip-audit and fails on any known vulnerability; Dependabot
  proposes dependency and GitHub Actions updates weekly.
- Added SECURITY.md describing how to report vulnerabilities privately.
- Only HTTPS pages on the hosts an outlet allows are fetched. Every redirect is checked again, and
  URLs that name private or reserved network addresses are refused.
- XML from websites is parsed with entity expansion, DTD loading and network access turned off.
  Response sizes are capped after decompression (64 MiB by default), which stops compression bombs.
- In the CSV files `trnews` writes, a text cell that a spreadsheet would run as a formula (it
  starts with `=`, `+`, `-`, `@`, a tab or a carriage return) begins with an apostrophe. Text
  taken from web pages then can't run as a formula when the file opens in Excel. `trnews fetch`
  removes the apostrophe again on reading, and JSONL and Parquet keep every value as it is.

### Migrating from 0.1.0
0.1.0 scraped the search pages of five outlets and returned a pandas DataFrame:

```python
from tr_news_scraper import tr_news_scraper as tns

df = tns.NewsScraper(page_limit=20).scrape(["deprem"])
```

That module is gone. 1.0 replaces it with `search()`, which finds articles for keywords in a date
range, and `fetch()`, which downloads the text of the articles you keep. Both respect each site's
robots.txt. Instead of a page limit, you give the date range:

```python
from tr_news_scraper import fetch, search

result = search(["deprem"], "2023-02-01", "2023-03-01")
df = result.articles  # every match: outlet, month, day, title, url, matched, reasons, ...

fetched = fetch(result)  # or fetch(df[df.outlet == "star"]) for a subset
df = fetched.articles  # with text, author and the publication time
```

The columns 0.1.0 returned map like this:
- `title` and `url` keep their names.
- `text` → `text`, and `authors` → `author`, after `fetch()`.
- `publish_date` and `meta_published_date` → `published`, after `fetch()`. In 0.1.0's last live
  run `publish_date` was empty on every article.
- `date`, the date on the search page → `day`, or `month` for archives that date only to the
  month.
- `keyword` → `matched`, which lists every keyword the article matched.
- `keywords`, `top_img`, `meta_img`, `meta_url`, `meta_description` and `meta_keywords` are gone.
  1.0 downloads no images and doesn't guess keywords from the text.

## [0.1.0] - 2024-01-10

### Added
- First release: `NewsScraper` collects news articles from CNN Türk, Hürriyet, Milliyet, Sabah and
  Posta for one or more keywords.

[Unreleased]: https://github.com/demirogun/tr-news-scraper/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/demirogun/tr-news-scraper/releases/tag/v0.1.0
