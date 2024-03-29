[![PyPI Latest Release](https://img.shields.io/pypi/v/tr-news-scraper.svg)](https://pypi.org/project/tr-news-scraper/) [![PyPI Downloads](https://img.shields.io/pypi/dm/tr-news-scraper.svg?label=PyPI%20downloads)](https://pypi.org/project/tr-news-scraper/) [![PyPI Downloads](https://img.shields.io/pypi/dw/tr-news-scraper.svg?label=PyPI%20downloads)](https://pypi.org/project/tr-news-scraper/) [![DOI](https://zenodo.org/badge/741400320.svg)](https://zenodo.org/doi/10.5281/zenodo.10509649) [![License - MIT](https://img.shields.io/pypi/l/tr-news-scraper.svg)](https://github.com/demirogun/tr-news-scraper/blob/main/LICENSE)

# tr-news-scraper

tr-news-scraper is a Python library that allows users to scrape Turkish news articles based on specified keywords from multiple sources. It gather news content from various news websites, enabling users to extract valuable information for analysis or research purposes.

## Installation

Use the package manager [pip](https://pip.pypa.io/en/stable/) to install this library.

```bash
pip install tr-news-scraper
```

## Usage

Scrape news articles based on a single or multiple keywords. scrape() method returns a **pandas dataframe**.

```python

from tr_news_scraper import tr_news_scraper as tns

scraper = tns.NewsScraper() # You can define page_limit parameter here. Default value is 20.
single_keyword_news = scraper.scrape(["keyword"]) # You can define keyword or keywords here.
multiple_keywords_news = scraper.scrape(["keyword_1", "keyword_2", "keyword_3"]) # You can define keyword or keywords here.
```
| title | authors | publish_date | text | keywords | top_img | url | meta_url | meta_img | meta_published_date | meta_description | meta_keywords | date | keyword |
|-------|---------|--------------|------|----------|---------|-----|----------|----------|---------------------|------------------|---------------|------|---------|
| title_1 | authors_1 | publish_date_1 | text_1 | keywords_1 | top_img_1 | url_1 | meta_url_1 | meta_img_1 | meta_published_date_1 | meta_description_1 | meta_keywords_1 | date_1 | keyword_1 |
| title_2 | authors_2 | publish_date_2 | text_2 | keywords_2 | top_img_2 | url_2 | meta_url_2 | meta_img_2 | meta_published_date_2 | meta_description_2 | meta_keywords_2 | date_2 | keyword_2 |
| title_3 | authors_3 | publish_date_3 | text_3 | keywords_3 | top_img_3 | url_3 | meta_url_3 | meta_img_3 | meta_published_date_3 | meta_description_3 | meta_keywords_3 | date_3 | keyword_3 |
| title_4 | authors_4 | publish_date_4 | text_4 | keywords_4 | top_img_4 | url_4 | meta_url_4 | meta_img_4 | meta_published_date_4 | meta_description_4 | meta_keywords_4 | date_4 | keyword_4 |
| title_5 | authors_5 | publish_date_5 | text_5 | keywords_5 | top_img_5 | url_5 | meta_url_5 | meta_img_5 | meta_published_date_5 | meta_description_5 | meta_keywords_5 | date_5 | keyword_5 |

## Sources

- [CNN Türk](https://www.cnnturk.com/)
- [Hürriyet](https://www.hurriyet.com.tr/)
- [Milliyet](https://www.milliyet.com.tr/)
- [Sabah](https://www.sabah.com.tr/)
- [Posta](https://www.posta.com.tr/)

## Citiation
APA
```
Demir, O., & Avcıoğlu, A. (2024). tr-news-scraper: Turkish news articles scraper based on specified keywords (Version 0.1.0) [Software]. https://github.com/demirogun/tr-news-scraper
```
BibTeX
```
@software{tr-news-scraper,
  author = {Ogün Demir and Aydoğan Avcı},
  title = {{tr-news-scrape}},
  version = {0.1.0},
  url = {https://github.com/demirogun/tr-news-scraper},
  year = {2024}
}
```