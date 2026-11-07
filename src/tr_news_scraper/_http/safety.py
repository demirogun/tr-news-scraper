"""URL rules: what the http layer is willing to fetch at all."""

from __future__ import annotations

from collections.abc import Collection
from urllib.parse import urlsplit

from tr_news_scraper.errors import HostNotAllowed


def check_url(url: str, allowed_hosts: Collection[str]) -> None:
    """Raise ``HostNotAllowed`` unless ``url`` is HTTPS and its host is in ``allowed_hosts``."""
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise HostNotAllowed(url, "only https URLs are fetched")
    host = parts.hostname or ""
    if host not in {allowed.lower() for allowed in allowed_hosts}:
        raise HostNotAllowed(url, f"{host or 'a URL without a host'} is not an allowed host")
