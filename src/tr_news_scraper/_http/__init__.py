"""The only way tr_news_scraper touches the network (internal).

Every request goes through :class:`Http`, which identifies the library honestly and only talks
to HTTPS hosts the caller allows.
"""

from tr_news_scraper._http.client import Http, HttpConfig, Response

__all__ = ["Http", "HttpConfig", "Response"]
