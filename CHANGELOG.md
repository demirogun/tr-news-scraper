# Changelog

All notable changes to tr-news-scraper are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
