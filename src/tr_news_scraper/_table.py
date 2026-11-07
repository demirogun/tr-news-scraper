"""The search result's rows and tables (internal).

Each outlet's run produces plain ``Row`` records. Only the functions that build DataFrames import
pandas, so ``import tr_news_scraper`` stays light.
"""

from __future__ import annotations

import html
import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from typing import TYPE_CHECKING
from urllib.parse import urlsplit, urlunsplit

from tr_news_scraper.outlets import Month, Outlet
from tr_news_scraper.outlets._dates import ISTANBUL
from tr_news_scraper.outlets._model import Gap

if TYPE_CHECKING:
    import pandas as pd

ARTICLE_COLUMNS = (
    "outlet",
    "month",
    "day",
    "title",
    "url",
    "matched",
    "reasons",
    "lastmod",
    "source",
)
GAP_COLUMNS = ("outlet", "reason", "month", "keyword", "detail", "url")
DAY_DTYPE = "datetime64[ns]"
TIME_DTYPE = "datetime64[ns, Europe/Istanbul]"

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


def merge(rows: Iterable[Row], keywords: Sequence[str], order: Mapping[str, int]) -> list[Row]:
    """One row per URL (S6), sorted by month, outlet, day and URL (S7).

    A URL found more than once keeps the earliest month, the first title, day and last-edit time
    found, and every keyword and reason, in query order and without repeats. ``order`` gives each
    outlet's position in the search.
    """
    found = sorted(
        enumerate(rows), key=lambda item: (item[1].month, order[item[1].outlet], item[0])
    )
    by_url: dict[str, Row] = {}
    for _, row in found:
        kept = by_url.get(row.url)
        by_url[row.url] = row if kept is None else _combine(kept, row, keywords)
    return sorted(
        by_url.values(),
        key=lambda row: (
            row.month,
            order[row.outlet],
            row.day is None,
            row.day or date.min,
            row.url,
        ),
    )


def _combine(kept: Row, other: Row, keywords: Sequence[str]) -> Row:
    found = set(kept.matched) | set(other.matched)
    return replace(
        kept,
        matched=tuple(keyword for keyword in keywords if keyword in found),
        reasons=tuple(dict.fromkeys((*kept.reasons, *other.reasons))),
        title=kept.title if kept.title is not None else other.title,
        day=kept.day if kept.day is not None else other.day,
        lastmod=kept.lastmod if kept.lastmod is not None else other.lastmod,
    )


def articles_frame(rows: Sequence[Row]) -> pd.DataFrame:
    """The article table: the spec's columns and dtypes, on pandas 2 and 3 alike."""
    import pandas as pd

    return pd.DataFrame(
        {
            "outlet": _strings([row.outlet for row in rows]),
            "month": _strings([str(row.month) for row in rows]),
            "day": _times([row.day for row in rows], DAY_DTYPE),
            "title": _strings([row.title for row in rows]),
            "url": _strings([row.url for row in rows]),
            "matched": _strings([", ".join(row.matched) for row in rows]),
            "reasons": _strings(["; ".join(row.reasons) for row in rows]),
            "lastmod": _times([row.lastmod for row in rows], TIME_DTYPE),
            "source": _strings([row.source for row in rows]),
        }
    )


def gaps_frame(runs: Sequence[OutletRun]) -> pd.DataFrame:
    """One row per gap, outlet by outlet in the order searched."""
    import pandas as pd

    gaps = [(run.outlet.id, gap) for run in runs for gap in run.gaps]
    return pd.DataFrame(
        {
            "outlet": _strings([outlet for outlet, _ in gaps]),
            "reason": _strings([gap.reason for _, gap in gaps]),
            "month": _strings([None if gap.month is None else str(gap.month) for _, gap in gaps]),
            "keyword": _strings([gap.keyword for _, gap in gaps]),
            "detail": _strings([gap.detail for _, gap in gaps]),
            "url": _strings([gap.url for _, gap in gaps]),
        }
    )


def _strings(values: Sequence[str | None]) -> pd.Series:
    import pandas as pd

    return pd.Series(values, dtype="string")


def _times(values: Sequence[date | datetime | None], dtype: str) -> pd.Series:
    import pandas as pd

    return pd.Series(
        [pd.NaT if value is None else pd.Timestamp(value) for value in values], dtype=dtype
    )
