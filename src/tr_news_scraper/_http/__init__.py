"""The only way tr_news_scraper touches the network (internal).

Every request goes through :class:`Http`, which identifies the library honestly, obeys
robots.txt (RFC 9309), paces requests per host, bounds retries, sizes and redirects, only talks
to public HTTPS hosts the caller allows, and caches successful responses on disk.
"""

from tr_news_scraper._http.cache import CachePolicy
from tr_news_scraper._http.client import HostStats, Http, HttpConfig, Response

__all__ = ["CachePolicy", "HostStats", "Http", "HttpConfig", "Response"]
