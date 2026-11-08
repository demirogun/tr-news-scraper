[![PyPI Latest Release](https://img.shields.io/pypi/v/tr-news-scraper.svg)](https://pypi.org/project/tr-news-scraper/) [![Python versions](https://img.shields.io/pypi/pyversions/tr-news-scraper.svg)](https://pypi.org/project/tr-news-scraper/) [![CI](https://github.com/demirogun/tr-news-scraper/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/demirogun/tr-news-scraper/actions/workflows/ci.yml) [![PyPI Downloads](https://img.shields.io/pypi/dm/tr-news-scraper.svg?label=PyPI%20downloads)](https://pypi.org/project/tr-news-scraper/) [![DOI](https://zenodo.org/badge/741400320.svg)](https://zenodo.org/doi/10.5281/zenodo.10509649) [![License - MIT](https://img.shields.io/github/license/demirogun/tr-news-scraper.svg)](https://github.com/demirogun/tr-news-scraper/blob/main/LICENSE)

# tr-news-scraper

Search Turkish news archives by keyword and date range, politely. tr-news-scraper finds the
articles seven Turkish-language outlets published about your keywords, reads their text, author
and publication time, and tells you what each outlet could and couldn't provide. It obeys every
site's robots.txt and sends each site one request per second.

## Türkçe özet

tr-news-scraper, Türkçe haber sitelerinin arşivlerinde anahtar kelime ve tarih aralığıyla haber
arar. Her sitenin robots.txt kurallarına uyar, her siteye saniyede en fazla bir istek gönderir ve
her haber kaynağı için neleri bulduğunu, neleri okuyamadığını raporlar. Bulduğu haberlerin
metnini, yazarını ve yayın zamanını da okuyabilir.

```bash
pip install tr-news-scraper
trnews search deprem --from 2023-02-01 --to 2023-02-28 --fetch --separator ";" -o deprem.csv
```

Bu komut haberleri ve metinlerini `deprem.csv` dosyasına yazar. `--separator ";"`, dosyanın
Türkçe bölge ayarlarıyla çalışan Excel'de doğru açılmasını sağlar. Python ile kullanım, haber
kaynakları ve sorumlu kullanım ilkeleri aşağıda İngilizce olarak anlatılmaktadır.

## Install

tr-news-scraper needs Python 3.12 or newer, on Windows, macOS or Linux.

```bash
pip install tr-news-scraper
```

For Parquet files, add the `parquet` extra: `pip install "tr-news-scraper[parquet]"`.

## Quick start

In Python, `search()` finds the articles and `fetch()` reads them:

```python
from tr_news_scraper import fetch, search

result = search(["deprem", "tsunami"], "2023-02-01", "2023-03-01")
print(result)  # how many articles each outlet found, and why some found none
result.articles  # one row per article: outlet, month, day, title, url, matched, ...

fetched = fetch(result)  # or fetch(result.articles.head(100)) for a sample
print(fetched)  # what each outlet read, and what failed
fetched.articles  # search's columns plus published, author, text, ...
```

The end date is excluded: `"2023-03-01"` above means up to and including 28 February. Days are
in Türkiye's time zone. A keyword of five letters or more also matches longer words (`deprem`
finds `depremzede`); `word*` forces that, and `"word"` matches the exact word only.

The same from a terminal, where `--to` is the last day and is included:

```bash
trnews search deprem tsunami --from 2023-02-01 --to 2023-02-28 -o deprem.csv
trnews fetch deprem.csv -o deprem-text.jsonl
trnews search deprem --from 2023-02-01 --to 2023-02-28 --fetch -o deprem-all.parquet
trnews coverage --check
```

- Tables go to `.csv` (UTF-8, ready for Excel), `.jsonl` or `.parquet` (with the `parquet`
  extra) files, never to the terminal.
- Beside every table, `NAME.report.json` records what was searched, when, with which version,
  and what each outlet reported.
- `trnews fetch` takes its keywords and range from that file, so searching and fetching in two
  steps gives the same rows as `--fetch`.
- No file is replaced without `--overwrite`.
- `trnews --help` lists every option.

## What you get

`search()` returns a `SearchResult`. `result.articles` has one row per article:

| Column | What it holds |
|---|---|
| `outlet` | the outlet's id, such as `trt-haber` |
| `month` | the archive month that lists the article, as `YYYY-MM` |
| `day` | the publication day, when the archive gives it (Milliyet); empty until `fetch()` otherwise |
| `title` | the headline, when the archive gives one; `fetch()` fills the rest from each page |
| `url` | the article's address, unique in the table |
| `matched` | the keywords that matched, such as `deprem, tsunami` |
| `reasons` | why each one matched, such as `url: 'depremin' matches 'deprem' (prefix)` |
| `lastmod` | when the archive says the page was last edited, not when it was published |
| `source` | the sitemap file or search page that listed it |

`result.report` has one row per outlet. Its `status` is `ok`, `incomplete` or `failed`, and
`coverage` says how much of the range the outlet's archive holds. `detail` says why, such as "the
archive starts in 2023-12". `result.gaps` lists every part of the range that couldn't be read,
and why.

`fetch()` returns a `FetchResult`. It adds these columns to `fetched.articles`:

| Column | What it holds |
|---|---|
| `published` | the page's original publication time, in Türkiye's time zone |
| `author` | the byline, as the page gives it |
| `text` | the article's text |
| `text_matched` | the keywords found in the text |
| `copy_group` | the same number for every copy of one story, such as one wire report in several outlets |
| `fetched_at` | when the page was downloaded |
| `error` | why the article couldn't be read, such as "robots.txt disallows it"; empty when it was |

Archives that date articles only to the month can list articles from outside your range.
`fetch()` reads each page's own date and moves those rows to `fetched.outside`, so nothing
disappears. `fetched.report` counts what each outlet read, took from the cache, or failed to
read.

Nothing fails silently. When every outlet fails, `search()` raises `SearchFailed` with each
outlet's reason, and `fetch()` raises `FetchFailed` when no article could be read.

## Outlets

| Outlet | `id` | Archive | From | Headlines |
|---|---|---|---|---|
| Cumhuriyet | `cumhuriyet` | monthly sitemap | 1962-08 | no |
| Euronews Türkçe | `euronews-tr` | monthly sitemap | 2010-01 | no |
| TRT Haber | `trt-haber` | monthly sitemap | 2016-07 | no |
| Star | `star` | monthly sitemap | 2012-09 | image titles |
| Akşam | `aksam` | monthly sitemap | 2010-12 | no |
| Sözcü | `sozcu` | monthly sitemap | 2023-12 | no |
| Milliyet | `milliyet` | site search | — | search results |

- **Cumhuriyet:** Every month since July 2008; only scattered months before. No headlines.
- **Euronews Türkçe:** Matched on URLs only: the titles in its sitemaps describe photos, not articles.
- **TRT Haber:** Lists article URLs without headlines.
- **Star:** Headlines come from the image titles in its sitemaps.
- **Akşam:** Lists article URLs without headlines.
- **Sözcü:** Sözcü's new website, from December 2023; older articles aren't in its archive.
- **Milliyet:** Milliyet's search returns only its newest 10,000 results for each keyword; for a frequent word like 'deprem' that reaches back about two and a half years.

Every outlet's archive is allowed by its robots.txt. Where an archive has no headlines, articles
are matched on their URLs; after `fetch()`, `text_matched` shows which keywords each text names.

`coverage()` lists the same without a request, and `coverage(check=True)` checks each archive now.
A weekly check on GitHub reads every outlet's real archive and opens an issue when one breaks.

You can add an outlet that publishes monthly sitemaps by describing it, without writing code:

```python
from tr_news_scraper import search
from tr_news_scraper.outlets import MonthlySitemap, builtin

haber = MonthlySitemap(
    id="haber",
    name="Haber",
    index="https://haber.example/sitemaps/index.xml",
    month_file=r"/sitemaps/posts-(?P<year>\d{4})-(?P<month>\d{2})\.xml$",
)
result = search("deprem", "2023-02-01", "2023-03-01", outlets=[*builtin(), haber])
```

## Responsible use

tr-news-scraper is built to be a good guest on the sites it reads. Please use it the same way.

- **robots.txt is obeyed.** Every request is checked against the site's robots.txt (RFC 9309).
  `obey_robots=False`, or `--ignore-robots-txt`, turns that off and warns. Use it only with the
  site's permission: you are responsible for those requests.
- **It says who it is.** Every request carries the User-Agent
  `tr-news-scraper/<version> (+https://github.com/demirogun/tr-news-scraper)`, which can't be
  changed or disguised. Add a way to reach you with `contact="mailto:you@example.org"` or
  `--contact`; it's never written to files.
- **It's slow on purpose.** Each site gets one request per second, longer if its robots.txt asks,
  and failures are retried at most three times. Please don't run several copies at once to go
  faster.
- **It keeps a cache.** Responses and the text read from each article are kept in your user cache
  folder, so the same search or fetch doesn't download everything again. That's
  `%LOCALAPPDATA%\tr-news-scraper\tr-news-scraper\Cache` on Windows,
  `~/Library/Caches/tr-news-scraper` on macOS and `~/.cache/tr-news-scraper` on Linux, at most 2
  GiB. `cache_dir=`, or `--cache-dir`, chooses another folder. Delete the folder to clear it.
- **The articles belong to their publishers.** Copyright law applies, such as Türkiye's Law No.
  5846 on Intellectual and Artistic Works, and so do each site's terms. Share URLs, metadata and
  the results you derive, such as counts and labels, rather than the articles' texts.
- **News names people.** Data protection law, such as Türkiye's KVKK (Law No. 6698) and the EU's
  GDPR, can apply to datasets built from news. Check your institution's rules before collecting
  data about individuals.
- **Publishers can opt out.** If you run one of these sites and want it left out, please open an
  issue: https://github.com/demirogun/tr-news-scraper/issues

This section explains how the tool is meant to be used. It isn't legal advice.

## Limits

- Sitemap archives date articles only to the month until `fetch()` reads each page.
- Milliyet's search returns only its newest 10,000 results for each keyword.
- Search matches URLs and headlines, so an article that names a keyword only in its text isn't
  found. Synonyms aren't added: search for `heyelan` and `toprak kayma` together. The CHANGELOG
  lists the other known limits.
- Websites change. When an outlet's archive moves, its results stop until a release follows it;
  the weekly check catches that.

## Citing

If you use tr-news-scraper in research, please cite it. GitHub's "Cite this repository" button
gives APA and BibTeX from
[CITATION.cff](https://github.com/demirogun/tr-news-scraper/blob/main/CITATION.cff), and Zenodo
archives every release under the DOI
[10.5281/zenodo.10509649](https://doi.org/10.5281/zenodo.10509649):

```bibtex
@software{tr_news_scraper,
  author    = {Demir, Ogün and Avcıoğlu, Aydoğan},
  title     = {tr-news-scraper},
  publisher = {Zenodo},
  doi       = {10.5281/zenodo.10509649},
  url       = {https://github.com/demirogun/tr-news-scraper}
}
```

That DOI always resolves to the latest version. To cite the version you used, take its own DOI
from Zenodo.

## Migrating from 0.1.0

0.1.0's `NewsScraper` is gone: it read search pages that robots.txt disallows, returned empty
tables, and pinned dependencies with known vulnerabilities. Use `search()` and `fetch()` instead.
The CHANGELOG maps every old column to its new one:
[Migrating from 0.1.0](https://github.com/demirogun/tr-news-scraper/blob/main/CHANGELOG.md#migrating-from-010).

## Development

```bash
git clone https://github.com/demirogun/tr-news-scraper
cd tr-news-scraper
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

The tests run offline, on recorded archives and page skeletons. `uv run pytest -m live
tests/live` reads the real sites; it runs weekly on GitHub, so please run it sparingly. Report
security problems privately, as
[SECURITY.md](https://github.com/demirogun/tr-news-scraper/blob/main/SECURITY.md) describes.

## License

MIT. See [LICENSE](https://github.com/demirogun/tr-news-scraper/blob/main/LICENSE).
