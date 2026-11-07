"""The data the outlets module works with: months, article candidates and outlet definitions."""

from __future__ import annotations

import re
from collections.abc import Collection
from dataclasses import dataclass, field
from datetime import MAXYEAR, MINYEAR, date, datetime, timedelta
from typing import Literal
from urllib.parse import urlsplit

from lxml import etree

from tr_news_scraper._http.safety import check_public_https, normalize_host
from tr_news_scraper.errors import HostNotAllowed

_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_SAMPLE_DAY = date(2023, 2, 6)


@dataclass(frozen=True, slots=True, order=True)
class Month:
    """A calendar month, such as ``Month(2023, 2)``. Months are ordered and hashable."""

    year: int
    month: int

    def __post_init__(self) -> None:
        if not MINYEAR <= self.year <= MAXYEAR or not 1 <= self.month <= 12:
            raise ValueError(f"{self.year}-{self.month} is not a calendar month")

    @classmethod
    def of(cls, day: date) -> Month:
        """The month ``day`` falls in."""
        return cls(day.year, day.month)

    @classmethod
    def span(cls, start: date, end: date) -> list[Month]:
        """Every month the range ``[start, end)`` touches, oldest first."""
        if start >= end:
            raise ValueError(f"the start ({start}) must be before the end ({end})")
        last = cls.of(end - timedelta(days=1))
        months = [cls.of(start)]
        while months[-1] < last:
            months.append(months[-1].next())
        return months

    @property
    def start(self) -> date:
        """The first day of the month."""
        return date(self.year, self.month, 1)

    def next(self) -> Month:
        """The month after this one."""
        if self.month == 12:
            return Month(self.year + 1, 1)
        return Month(self.year, self.month + 1)

    def previous(self) -> Month:
        """The month before this one."""
        if self.month == 1:
            return Month(self.year - 1, 12)
        return Month(self.year, self.month - 1)

    def __str__(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"


@dataclass(frozen=True, slots=True)
class Candidate:
    """An article that an outlet's archive lists, before any keyword matching."""

    outlet: str
    """The outlet's id."""
    url: str
    """The article URL: HTTPS, on one of the outlet's hosts, without surrounding whitespace."""
    month: Month
    """The archive month that listed the article; for search results, the month of ``day``."""
    title: str | None = None
    """The headline, when the archive lists real headlines (never a photo caption)."""
    day: date | None = None
    """The publication day, when the archive states it (site search)."""
    lastmod: datetime | None = None
    """The sitemap's last-edit time (timezone-aware). It isn't the publication time."""
    source: str = ""
    """The archive URL the article came from."""


@dataclass(frozen=True, slots=True)
class MonthlySitemap:
    """An outlet whose sitemap index lists one sitemap file per month.

    Only the months the index lists are ever read, so no file URL is guessed::

        MonthlySitemap(
            id="trt-haber",
            name="TRT Haber",
            index="https://www.trthaber.com/sitemaps/news.xml",
            month_file=r"/sitemaps/news-(?P<year>\\d{4})-(?P<month>\\d{2})\\.xml$",
        )
    """

    id: str
    """Lowercase kebab-case, unique among outlets: ``"trt-haber"``."""
    name: str
    """Display name: ``"TRT Haber"``."""
    index: str
    """HTTPS URL of the sitemap index that lists the monthly files."""
    month_file: str
    """Regex with named groups ``year`` and ``month``, searched in each ``<loc>`` of the index."""
    titles: Literal["image"] | None = None
    """``"image"`` when ``<image:title>`` holds the article's headline (checked per outlet)."""
    earliest: Month | None = None
    """The first month with articles, as verified; shown by coverage and checked weekly."""
    extra_hosts: frozenset[str] = frozenset()
    """Hosts besides the index's own host that article URLs may use."""
    notes: str = ""
    """One or two sentences about the archive, shown by coverage."""
    hosts: frozenset[str] = field(init=False, compare=False, repr=False)
    """Every host this outlet's requests and article URLs may use (IDNA, lowercase)."""
    pattern: re.Pattern[str] = field(init=False, compare=False, repr=False)
    """``month_file``, compiled."""

    def __post_init__(self) -> None:
        _check_identity(self.id, self.name)
        index_host = _https_host("index", self.index)
        try:
            pattern = re.compile(self.month_file)
        except re.error as error:
            raise ValueError(f"month_file isn't a valid regular expression: {error}") from None
        if not {"year", "month"} <= set(pattern.groupindex):
            raise ValueError("month_file needs the named groups 'year' and 'month'")
        if self.titles not in (None, "image"):
            raise ValueError("titles must be None or 'image'")
        if self.earliest is not None and not isinstance(self.earliest, Month):
            raise ValueError("earliest must be a Month, such as Month(2010, 12)")
        object.__setattr__(self, "extra_hosts", _host_set(self.extra_hosts))
        object.__setattr__(self, "hosts", self.extra_hosts | {normalize_host(index_host)})
        object.__setattr__(self, "pattern", pattern)

    @property
    def method(self) -> str:
        """How the outlet's archive is read, for coverage reports."""
        return "monthly sitemap"

    def accepts(self, url: str) -> bool:
        """Whether ``url`` may be an article of this outlet: HTTPS on one of its hosts."""
        return _accepts(url, self.hosts)


@dataclass(frozen=True, slots=True)
class SiteSearch:
    """An outlet whose search endpoint, allowed by robots.txt, returns pages of results with
    the newest first. An empty page means the results have ended.

    The XPaths say where each result's parts are. ``item`` selects the results on a page;
    ``link``, ``date`` and ``title`` are relative to one result and may select an attribute or
    an element (whose text is used).
    """

    id: str
    name: str
    url: str
    """HTTPS URL template with ``{query}`` and ``{page}``."""
    item: str
    link: str
    date: str
    date_format: str
    """``strptime`` format of the date text, such as ``"%d.%m.%Y"``."""
    title: str | None = None
    max_pages: int = 1000
    """The most pages considered; results usually end sooner, at an empty page."""
    extra_hosts: frozenset[str] = frozenset()
    notes: str = ""
    hosts: frozenset[str] = field(init=False, compare=False, repr=False)
    xpaths: dict[str, etree.XPath] = field(init=False, compare=False, repr=False)
    """The compiled XPaths, by field name."""

    def __post_init__(self) -> None:
        _check_identity(self.id, self.name)
        for placeholder in ("{query}", "{page}"):
            if placeholder not in self.url:
                raise ValueError(f"url must contain {placeholder}")
        url_host = _https_host("url", self.url.replace("{query}", "q").replace("{page}", "1"))
        expressions = {"item": self.item, "link": self.link, "date": self.date}
        if self.title is not None:
            expressions["title"] = self.title
        compiled: dict[str, etree.XPath] = {}
        for name, expression in expressions.items():
            try:
                compiled[name] = etree.XPath(expression)
            except etree.XPathSyntaxError as error:
                raise ValueError(f"{name} isn't a valid XPath: {error}") from None
        if not _reads_full_dates(self.date_format):
            raise ValueError("date_format must read a full date, such as '%d.%m.%Y'")
        if isinstance(self.max_pages, bool) or not isinstance(self.max_pages, int):
            raise ValueError("max_pages must be a whole number")
        if self.max_pages < 1:
            raise ValueError("max_pages must be at least 1")
        object.__setattr__(self, "extra_hosts", _host_set(self.extra_hosts))
        object.__setattr__(self, "hosts", self.extra_hosts | {normalize_host(url_host)})
        object.__setattr__(self, "xpaths", compiled)

    @property
    def method(self) -> str:
        """How the outlet's archive is read, for coverage reports."""
        return "site search"

    def accepts(self, url: str) -> bool:
        """Whether ``url`` may be an article of this outlet: HTTPS on one of its hosts."""
        return _accepts(url, self.hosts)


Outlet = MonthlySitemap | SiteSearch
"""Any outlet definition."""


def _check_identity(outlet_id: str, name: str) -> None:
    if not isinstance(outlet_id, str) or not _ID.fullmatch(outlet_id):
        raise ValueError(f"id must be lowercase kebab-case, like 'trt-haber', not {outlet_id!r}")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("name can't be blank")


def _https_host(field_name: str, url: str) -> str:
    try:
        return check_public_https(url)
    except HostNotAllowed as error:
        raise ValueError(f"{field_name} must be an https URL on a public host: {error}") from None


def _reads_full_dates(fmt: str) -> bool:
    """Whether ``fmt`` round-trips a full date (day, month and year)."""
    try:
        # Only checks a format; there is no time zone to attach.
        parsed = datetime.strptime(_SAMPLE_DAY.strftime(fmt), fmt)  # noqa: DTZ007
    except ValueError:
        return False
    return parsed.date() == _SAMPLE_DAY


def _host_set(hosts: Collection[str]) -> frozenset[str]:
    if isinstance(hosts, str):
        raise ValueError("extra_hosts must be a collection of host names, not one string")
    if not all(isinstance(host, str) and host.strip() for host in hosts):
        raise ValueError("extra_hosts must contain host names only")
    return frozenset(normalize_host(host) for host in hosts)


def _accepts(url: str, hosts: frozenset[str]) -> bool:
    try:
        parts = urlsplit(url)
        host = parts.hostname
    except ValueError:
        return False
    if parts.scheme != "https" or parts.username is not None or parts.password is not None:
        return False
    if not host:
        return False
    if host in hosts:
        return True
    return not host.isascii() and normalize_host(host) in hosts
