"""What the http layer is willing to fetch, and how it reads XML from strangers."""

from __future__ import annotations

import ipaddress
import zlib
from collections.abc import Collection
from urllib.parse import urlsplit

import idna
from lxml import etree

from tr_news_scraper.errors import HostNotAllowed, ResponseTooLarge

_GZIP_MAGIC = b"\x1f\x8b"


def normalize_host(host: str) -> str:
    """Lowercase a host and convert it to its IDNA (punycode) form: ``BÜCHER.example`` →
    ``xn--bcher-kva.example``. A trailing dot is dropped."""
    host = host.strip().rstrip(".").lower()
    try:
        return idna.encode(host, uts46=True).decode("ascii")
    except idna.IDNAError:
        return host


def check_public_https(url: str) -> str:
    """Raise ``HostNotAllowed`` unless ``url`` is HTTPS, has no user info, and doesn't name a
    private or reserved IP address. Returns the URL's host."""
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise HostNotAllowed(url, "only https URLs are fetched")
    if parts.username is not None or parts.password is not None:
        raise HostNotAllowed(url, "URLs with user info are refused")
    host = parts.hostname or ""
    if not host:
        raise HostNotAllowed(url, "the URL has no host")
    if _is_non_public_address(host):
        raise HostNotAllowed(url, f"{host} is a private or reserved address")
    return host


def check_url(url: str, allowed_hosts: Collection[str]) -> None:
    """Raise ``HostNotAllowed`` unless ``url`` passes ``check_public_https`` and its host is in
    ``allowed_hosts`` (compared in IDNA form)."""
    host = check_public_https(url)
    if normalize_host(host) not in {normalize_host(allowed) for allowed in allowed_hosts}:
        raise HostNotAllowed(url, f"{host} is not an allowed host")


def parse_xml(content: bytes, *, max_bytes: int, url: str) -> etree._Element:
    """Parse XML with entity expansion, DTD loading and network access turned off.

    Gzip-compressed bodies (``.xml.gz`` files) are decompressed first, under the same size cap
    as any response. Raises ``lxml.etree.XMLSyntaxError`` for malformed XML.
    """
    data = _gunzip(content, max_bytes, url) if content[:2] == _GZIP_MAGIC else content
    parser = etree.XMLParser(
        resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False
    )
    return etree.fromstring(data, parser=parser)


def _gunzip(data: bytes, limit: int, url: str) -> bytes:
    decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
    output = decompressor.decompress(data, limit + 1)
    if len(output) > limit or decompressor.unconsumed_tail:
        raise ResponseTooLarge(url, limit)
    return output


def _is_non_public_address(host: str) -> bool:
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return not address.is_global
