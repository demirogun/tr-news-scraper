# Changelog

All notable changes to tr-news-scraper are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

### Changed
- Requires Python 3.12 or newer. Python 3.10 reached end of life in October 2026, and the exact
  pins in 0.1.0 could not be installed on Python 3.13 or newer.
- Packaging is a single `pyproject.toml` (hatchling build backend), and the package uses the `src/`
  layout.
- Dependencies are declared as version ranges instead of 31 exact pins, so security fixes reach you
  without a new tr-news-scraper release.

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

### Migrating from 0.1.0
0.1.0 scraped the search pages of five outlets and returned a pandas DataFrame:

```python
from tr_news_scraper import tr_news_scraper as tns

df = tns.NewsScraper(page_limit=20).scrape(["deprem"])
```

That module is gone. 1.0 replaces it with `search()`, which finds articles for keywords in a date
range, and `fetch()`, which downloads the text of the articles you keep. Both respect each site's
robots.txt. The replacement API is still being built on the `v1-rewrite` branch, and this section
will show a complete example before 1.0.0 is released.

## [0.1.0] - 2024-01-10

### Added
- First release: `NewsScraper` collects news articles from CNN Türk, Hürriyet, Milliyet, Sabah and
  Posta for one or more keywords.

[Unreleased]: https://github.com/demirogun/tr-news-scraper/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/demirogun/tr-news-scraper/releases/tag/v0.1.0
