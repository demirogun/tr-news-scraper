"""Turkish news outlets and their archives: the plug-in API.

An outlet is data, not code: where its archive is and how to read it. One engine reads every
archive the same way, through the library's polite HTTP client.
"""

from tr_news_scraper.outlets._model import Month

__all__ = ["Month"]
