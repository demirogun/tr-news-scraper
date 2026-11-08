"""coverage(): what each outlet's archive holds, and whether it works today (internal)."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from tr_news_scraper._http import Http, HttpConfig
from tr_news_scraper._search import in_threads, resolve_outlets
from tr_news_scraper._table import string_series, time_series
from tr_news_scraper.outlets import Month, MonthlySitemap, Outlet
from tr_news_scraper.outlets._dates import ISTANBUL
from tr_news_scraper.outlets._health import check as health_check

if TYPE_CHECKING:
    import pandas as pd

COVERAGE_COLUMNS = ("outlet", "name", "method", "earliest", "headlines", "hosts", "notes")
HEALTH_COLUMNS = ("ok", "problems", "oldest", "newest", "sample", "checked_at")


def coverage(
    outlets: str | Outlet | Iterable[str | Outlet] | None = None,
    *,
    check: bool = False,
    contact: str | None = None,
    obey_robots: bool = True,
    cache_dir: str | Path | None = None,
) -> pd.DataFrame:
    """What each outlet's archive covers: one row per outlet, in the order given.

    >>> coverage()              # how each built-in outlet is read, and from when; no request
    >>> coverage(check=True)    # also checks every archive now: 2 requests per outlet

    The columns are ``outlet``, ``name``, ``method``, ``earliest`` (the first month of a
    monthly sitemap), ``headlines`` (``no``, ``image titles`` or ``search results``), ``hosts``
    and ``notes``. With ``check=True`` it reads each archive's index and last month, or the
    first two search pages, and adds ``ok``, ``problems``, ``oldest`` and ``newest`` (the
    months the index lists), ``sample`` and ``checked_at``. ``contact``, ``obey_robots`` and
    ``cache_dir`` work as in ``search()``.
    """
    chosen = resolve_outlets(outlets)
    config = HttpConfig(
        contact=contact,
        obey_robots=obey_robots,
        cache_dir=None if cache_dir is None else Path(cache_dir),
    )
    if not check:
        return _coverage(chosen, None, now=datetime.now(ISTANBUL))
    with Http(config) as http:
        return _coverage(chosen, http, now=datetime.now(ISTANBUL))


def _coverage(outlets: Sequence[Outlet], http: Http | None, *, now: datetime) -> pd.DataFrame:
    """``coverage()`` with the client given, or ``None`` for no health check (S10)."""
    import pandas as pd

    columns: dict[str, pd.Series] = {
        "outlet": string_series([outlet.id for outlet in outlets]),
        "name": string_series([outlet.name for outlet in outlets]),
        "method": string_series([outlet.method for outlet in outlets]),
        "earliest": string_series([_earliest(outlet) for outlet in outlets]),
        "headlines": string_series([_headlines(outlet) for outlet in outlets]),
        "hosts": string_series([", ".join(sorted(outlet.hosts)) for outlet in outlets]),
        "notes": string_series([outlet.notes for outlet in outlets]),
    }
    if http is not None:
        client, today = http, now.date()
        found = in_threads(
            outlets, client, lambda outlet: health_check(outlet, client, today=today)
        )
        columns |= {
            "ok": pd.Series([health.ok for health in found], dtype="bool"),
            "problems": string_series(["; ".join(health.problems) for health in found]),
            "oldest": string_series([_month(health.oldest) for health in found]),
            "newest": string_series([_month(health.newest) for health in found]),
            "sample": pd.Series([health.sample for health in found], dtype="int64"),
            "checked_at": time_series([now] * len(found)),
        }
    return pd.DataFrame(columns)


def _earliest(outlet: Outlet) -> str | None:
    return _month(outlet.earliest) if isinstance(outlet, MonthlySitemap) else None


def _headlines(outlet: Outlet) -> str:
    if isinstance(outlet, MonthlySitemap):
        return "image titles" if outlet.titles == "image" else "no"
    return "search results" if outlet.title is not None else "no"


def _month(month: Month | None) -> str | None:
    return None if month is None else str(month)
