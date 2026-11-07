"""The search result's rows and tables (internal).

Each outlet's run produces plain ``Row`` records. Only the functions that build DataFrames import
pandas, so ``import tr_news_scraper`` stays light.
"""

from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from urllib.parse import urlsplit, urlunsplit

from tr_news_scraper.outlets import Month, Outlet
from tr_news_scraper.outlets._dates import ISTANBUL
from tr_news_scraper.outlets._model import Gap

_SPACE = re.compile(r"\s+")
_DEFAULT_PORTS = {"https": 443, "http": 80}


@dataclass(frozen=True, slots=True)
class Row:
    """One matching article, before the table is built."""

    outlet: str
    url: str
    month: Month
    matched: tuple[str, ...]
    """The keywords that matched, in query order."""
    reasons: tuple[str, ...]
    """Every match's reason: title first, then URL."""
    source: str
    title: str | None = None
    day: date | None = None
    lastmod: datetime | None = None


@dataclass(slots=True)
class OutletRun:
    """What one outlet's scan produced: its rows, what it left out and why, and its gaps."""

    outlet: Outlet
    rows: list[Row] = field(default_factory=list)
    candidates: int = 0
    """Archive entries in the range's months, or search results in the range."""
    trimmed: int = 0
    """Matching entries left out by their dates (S4)."""
    unconfirmed: int = 0
    """Search results whose headline and URL name no keyword (S3)."""
    gaps: list[Gap] = field(default_factory=list)
    failure: str | None = None
    """Why nothing could be read, when the outlet failed."""


def clean_url(url: str) -> str:
    """Lowercase the scheme and host, and drop the default port and the fragment (S5).

    The path and the query are kept exactly. A URL whose port can't be read is only stripped.
    """
    text = url.strip()
    parts = urlsplit(text)
    try:
        port = parts.port
    except ValueError:
        return text
    scheme = parts.scheme.lower()
    host = parts.hostname or ""
    netloc = host if port is None or port == _DEFAULT_PORTS.get(scheme) else f"{host}:{port}"
    return urlunsplit((scheme, netloc, parts.path, parts.query, ""))


def clean_title(title: str | None) -> str | None:
    """Decode leftover HTML entities, collapse whitespace and normalize to NFC (S5). Some
    sitemaps escape their titles twice. An empty title becomes ``None``."""
    if title is None:
        return None
    text = unicodedata.normalize("NFC", _SPACE.sub(" ", html.unescape(title)).strip())
    return text or None


def clean_lastmod(lastmod: datetime | None) -> datetime | None:
    """The last-edit time in Europe/Istanbul, so the table's column has one time zone."""
    return None if lastmod is None else lastmod.astimezone(ISTANBUL)
