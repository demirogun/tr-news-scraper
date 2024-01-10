import requests
import time
import pandas as pd
from tqdm import tqdm
from newspaper import Article


class NewsScraper:
    def __init__(self, page_limit=20):
        """
        Initialize the NewsScraper class.

        Args:
        - page_limit (int): Limit the number of pages to scrape (default is 20).
        """
        self.keywords = None
        self.session = requests.Session()

        self.urls = []
        self.news = []
        self.news_df = None

        self.page_limit = page_limit

        self.local_news_cache = []
        self.local_url_cache = []

        self.error_log = []

    def scrape(self, keywords):
        """
        Scrape news content based on provided keywords.

        Args:
        - keywords (list): List of keywords to search for news articles.

        Returns:
        - pandas DataFrame: DataFrame containing scraped news content.
        """
        if isinstance(keywords, list):
            self.keywords = keywords
            print("Scraping news urls...")
            self._scrape_news_urls()

            print("Scraping news content...")
            for url in tqdm(self.urls):
                self._scrape_news_content(url)

            print("Creating dataframe...")
            self.news_df = pd.DataFrame(self.news)

            print("Cleaning duplicates...")
            self.news_df = self.news_df.drop_duplicates(subset=['url']).reset_index(drop=True)
            self.news_df = self.news_df.drop_duplicates(subset=['text']).reset_index(drop=True)

            print("Done!")
            return self.news_df
        else:
            raise Exception("Keywords must be list!")

    def _scrape_news_content(self, url):
        """
        Scrape content from a specific news article URL.

        Args:
        - url (str): URL of the news article to scrape.
        """
        if url['url'] in self.local_news_cache:
            pass
        else:
            try:
                article = Article(url['url'])
                article.download()
                article.parse()

                self.news.append({"title": article.title,
                                  'authors': ", ".join(article.authors),
                                  'publish_date': article.publish_date,
                                  'text': article.text,
                                  'keywords': article.keywords,
                                  'top_img': article.top_img,
                                  'url': article.url,
                                  'meta_url': article.meta_data['url'],
                                  'meta_img': article.meta_img,
                                  'meta_published_date': article.meta_data['datePublished'],
                                  'meta_description': article.meta_description,
                                  'meta_keywords': article.meta_keywords,
                                  'date': url['date'],
                                  'keyword': url['keyword']})

                self.local_news_cache.append(url['url'])
            except Exception as e:
                self.error_log.append({"url": url['url'], "error": e})

    def _scrape_news_urls(self):
        """
        Scrape news URLs from various sources based on provided keywords.
        """

        sources = [
            self._sabah_url_scraper,
            self._milliyet_url_scraper,
            self._hurriyet_url_scraper,
            self._posta_url_scraper
        ]

        for k in self.keywords:
            for i in tqdm(range(self.page_limit)):
                time.sleep(0.25)
                for source_scraper in sources:
                    try:
                        self.urls += source_scraper(k, i)
                    except Exception as e:
                        self.error_log.append({"url": f"{source_scraper.__name__}", "error": repr(e)})

            for i in tqdm(range(0, self.page_limit * 25, 50)):
                time.sleep(0.25)
                try:
                    self.urls += self._cnn_url_scraper(k, i, i + 50)
                except Exception as e:
                    self.error_log.append({"url": f"cnn_{k}_{i}", "error": e})

    def _sabah_url_scraper(self, keyword, page):
        url = f"https://www.sabah.com.tr/get/arama?query={keyword}&categorytype=haber&selectedcategory=yasam&page={page}"
        req = self.session.get(url)
        content = str(req.content)

        items = content.split('<div data-search-item class="col-lg-4 col-md-6 col-sm-6 view20 ">')
        items = items[1:]

        for item in items:
            date = item.split('<span class="info">')[1].split('|')[1].split('</span>')[0].strip()
            item_url = item.split('<a href="')[1].split('"')[0]
            if f"sabah_{item_url}" not in self.local_url_cache:
                if len(item_url.split("https://www.sabah.com.tr")) > 1:
                    self.urls.append({"url": item_url, "date": date})
                    self.local_url_cache.append(f"sabah_{item_url}")
                else:
                    self.urls.append({"url": f"https://www.sabah.com.tr{item_url}", "date": date, "keyword": keyword})
                    self.local_url_cache.append(f"sabah_{item_url}")

    def _milliyet_url_scraper(self, keyword, page):
        page = page + 1
        url = f"https://www.milliyet.com.tr/api/search/searchcontentloadmore?query={keyword}&page={page}&isFromNewsSearchPage=true"
        req = self.session.get(url)
        content = str(req.content)

        items = content.split('<div class="news__item col-md-12 col-sm-6">')
        items = items[1:]

        for item in items:
            date = item.split('<span class="news__date">')[1].split('</span>')[0]
            item_url = item.split('<a href="')[1].split('"')[0]
            if f"milliyet_{item_url}" not in self.local_url_cache:
                if len(item_url.split("https://www.milliyet.com.tr")) > 1:
                    pass
                elif len(item_url.split("/gundem/")) > 1:
                    self.urls.append(
                        {"url": f"https://www.milliyet.com.tr{item_url}", "date": date, "keyword": keyword})
                    self.local_url_cache.append(f"milliyet_{item_url}")

    def _hurriyet_url_scraper(self, keyword, page):
        url = f"https://www.hurriyet.com.tr/api/search/searchcontentloadmore?query={keyword}&page={page}&isFromNewsSearchPage=true"
        req = self.session.get(url)
        content = str(req.content)

        items = content.split('<div class="tag__list__item">')
        items = items[1:]

        for item in items:
            item_url = item.split('<a href="')[1].split('"')[0]
            if f"hurriyet_{item_url}" not in self.local_url_cache:
                if len(item_url.split("https://www.hurriyet.com.tr")) > 1:
                    pass
                elif len(item_url.split("/gundem/")) > 1:
                    self.urls.append(
                        {"url": f"https://www.hurriyet.com.tr{item_url}", "date": None, "keyword": keyword})
                    self.local_url_cache.append(f"hurriyet_{item_url}")

    def _cnn_url_scraper(self, keyword, start_page, end_page):
        url = f"https://www.cnnturk.com/api/lazy/loadmore?containerSize=col-12&url=/{keyword}&orderBy=StartDate%20desc&paths=&subPath=True&tags={keyword}&skip={start_page}&top={end_page}&contentTypes=Article&customTypes=&viewName=load-mixed-by-date&controlIxName="
        req = self.session.get(url)
        content = str(req.content)

        items = content.split('<div class="col-lg-4 col-md-6 col-sm-12">')
        items = items[1:]

        for item in items:
            date = item.split('data-last-start-date="')[1].split('"')[0]
            item_url = item.split('<a href="')[1].split('"')[0]
            if f"cnn_{item_url}" not in self.local_url_cache:
                if len(item_url.split("https://www.cnnturk.com.tr")) > 1:
                    self.urls.append({"url": item_url, "date": date})
                    self.local_url_cache.append(f"sabah_{item_url}")
                else:
                    self.urls.append({"url": f"https://www.cnnturk.com{item_url}", "date": date, "keyword": keyword})
                    self.local_url_cache.append(f"cnn_{item_url}")

    def _posta_url_scraper(self, keyword, page):
        page = page + 1
        url = f"https://www.posta.com.tr/api/search/searchcontentloadmore?query={keyword}&page={page}&isFromNewsSearchPage=true"
        req = self.session.get(url)
        content = str(req.content)

        items = content.split('<div class="news__item col-md-12 col-sm-6">')
        items = items[1:]

        for item in items:
            date = item.split('<span class="news__date">')[1].split('</span>')[0]
            item_url = item.split('<a href="')[1].split('"')[0]
            if f"posta_{item_url}" not in self.local_url_cache:
                if len(item_url.split("https://www.posta.com.tr")) > 1:
                    pass
                elif len(item_url.split("/gundem/")) > 1:
                    self.urls.append({"url": f"https://www.posta.com.tr{item_url}", "date": date, "keyword": keyword})
                    self.local_url_cache.append(f"posta_{item_url}")