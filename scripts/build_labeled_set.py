"""Build the draft labeled set for the matching accuracy gate (task T12 of the 1.0 rewrite).

Collects article headlines and URLs (metadata only, never article text) through
tr_news_scraper's own polite ``Http`` client (robots.txt obeyed, honest User-Agent):

- Euronews Türkçe's monthly archive sitemaps, which carry headlines, for months with major
  earthquakes, floods, landslides, avalanches and tsunamis;
- NTV's and TRT Haber's current news sitemaps, for everyday headlines;
- TRT Haber's monthly archives, which list URLs only: for the rare keywords (heyelan, çığ,
  tsunami, sel) a sample of matching URLs is fetched once to read each page's headline.

It samples about 300 rows. A label is pre-filled with 0 only where the keyword's root can't
occur (the folded root isn't in the folded headline); every other label is "?" for a person to
decide. The committed CSV holds Claude's draft decisions, marked ``reviewed=no`` until a
maintainer checks them. Usage::

    uv run python scripts/build_labeled_set.py tests/matching/fixtures/labeled.csv
"""

from __future__ import annotations

import csv
import random
import sys
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import lxml.html
from lxml import etree

from tr_news_scraper._http import Http
from tr_news_scraper.errors import TrNewsError

EURONEWS = "tr.euronews.com"
TRT = "www.trthaber.com"
EURONEWS_MONTHS = (
    "2020-02",  # Van avalanches
    "2020-10",  # İzmir earthquake and tsunami
    "2021-07",  # floods in Germany and Belgium
    "2021-08",  # Western Black Sea floods and landslides
    "2022-01",  # Tonga eruption and tsunami
    "2023-02",  # Kahramanmaraş earthquakes
    "2023-03",  # Şanlıurfa and Adıyaman floods
    "2023-09",  # Derna floods
    "2024-01",  # Noto earthquake and tsunami warnings
    "2024-02",  # İliç landslide
    "2024-05",  # Papua New Guinea landslide
    "2024-07",  # Wayanad landslides
    "2024-10",  # Valencia floods
    "2025-07",  # Kamchatka earthquake and tsunami warnings
)
TRT_MONTHS = (
    "2020-02",
    "2020-10",
    "2021-08",
    "2022-01",
    "2023-02",
    "2024-01",
    "2024-02",
    "2025-07",
)
CURRENT_SITEMAPS = {
    "www.ntv.com.tr": "https://www.ntv.com.tr/sitemaps/news-sitemap.xml",
    TRT: "https://www.trthaber.com/sitemap_haber.xml",
}
OUTLET_NAMES = {EURONEWS: "Euronews Türkçe", "www.ntv.com.tr": "NTV", TRT: "TRT Haber"}
ROOTS = {"deprem": "deprem", "sel": "sel", "heyelan": "heyelan", "cig": "cig", "tsunami": "tsunami"}
TITLED_QUOTAS = {"deprem": 40, "sel": 60, "heyelan": 40, "cig": 40, "tsunami": 40}
TRT_PAGE_QUOTAS = {"heyelan": 25, "cig": 30, "tsunami": 35, "sel": 15}
TRAPS = ("selam", "selcuk", "selin", "selim", "volkan", "kayak", "ciglik", "kisisel", "ciger")
TARGET_ROWS = 300
SEED = 20261107
NS = {
    "sm": "http://www.sitemaps.org/schemas/sitemap/0.9",
    "news": "http://www.google.com/schemas/sitemap-news/0.9",
    "image": "http://www.google.com/schemas/sitemap-image/1.1",
}
_TR_UPPER_I = str.maketrans({"İ": "i", "I": "ı"})
_FOLD = str.maketrans("çğıöşüâîû", "cgiosuaiu")


@dataclass(frozen=True, slots=True)
class Row:
    outlet: str
    url: str
    title: str


def fold(text: str) -> str:
    """Lowercase Turkish text correctly and drop its diacritics."""
    return unicodedata.normalize("NFC", text).translate(_TR_UPPER_I).lower().translate(_FOLD)


def entries(root: etree._Element) -> Iterator[tuple[str, str | None]]:
    """Yield ``(url, headline or None)`` for each sitemap entry."""
    for entry in root.iterfind("sm:url", NS):
        url = (entry.findtext("sm:loc", namespaces=NS) or "").strip()
        title = entry.findtext("news:news/news:title", namespaces=NS) or entry.findtext(
            "image:image/image:title", namespaces=NS
        )
        if url:
            yield url, " ".join(title.split()) if title else None


def headline(http: Http, url: str) -> str | None:
    """Read an article page's headline (og:title, else <title>), minus the site name."""
    try:
        page = lxml.html.fromstring(http.get(url, allowed_hosts={TRT}).text())
    except (TrNewsError, etree.ParserError):
        return None
    found = page.xpath("//meta[@property='og:title']/@content") or page.xpath("//title/text()")
    if not found:
        return None
    return " ".join(str(found[0]).split(" - TRT Haber")[0].split()) or None


def collect_titled(http: Http) -> dict[str, Row]:
    rows: dict[str, Row] = {}
    sources = [(f"https://{EURONEWS}/sitemap/articles-{m}.xml", EURONEWS) for m in EURONEWS_MONTHS]
    sources += [(url, host) for host, url in CURRENT_SITEMAPS.items()]
    for url, host in sources:
        for loc, title in entries(http.get(url, allowed_hosts={host}).xml()):
            if title:
                rows[loc] = Row(OUTLET_NAMES[host], loc, title)
        print(f"{url}: {len(rows)} titled rows so far")
    return rows


def collect_trt_pages(http: Http, rng: random.Random, skip: set[str]) -> dict[str, Row]:
    urls: list[str] = []
    for month in TRT_MONTHS:
        archive = f"https://{TRT}/sitemaps/news-{month}.xml"
        urls += [loc for loc, _ in entries(http.get(archive, allowed_hosts={TRT}).xml())]
        print(f"{archive}: {len(urls)} URLs so far")
    rows: dict[str, Row] = {}
    for column, quota in TRT_PAGE_QUOTAS.items():
        slug_hits = [u for u in urls if ROOTS[column] in u.rsplit("/", 1)[-1] and u not in skip]
        rng.shuffle(slug_hits)
        for url in slug_hits[:quota]:
            if url in rows:
                continue
            if title := headline(http, url):
                rows[url] = Row(OUTLET_NAMES[TRT], url, title)
        print(f"TRT pages for {column}: {len(rows)} headlines so far")
    return rows


def sample(titled: dict[str, Row], pages: dict[str, Row], rng: random.Random) -> list[Row]:
    rows = list(titled.values())
    chosen: dict[str, Row] = dict(pages)
    for column, root in ROOTS.items():
        candidates = [row for row in rows if root in fold(row.title)]
        rng.shuffle(candidates)
        chosen.update((row.url, row) for row in candidates[: TITLED_QUOTAS[column]])
    traps = [row for row in rows if set(TRAPS) & set(fold(row.title).replace("'", " ").split())]
    rng.shuffle(traps)
    chosen.update((row.url, row) for row in traps[:25])
    plain = [
        row
        for row in rows
        if row.url not in chosen and not any(root in fold(row.title) for root in ROOTS.values())
    ]
    rng.shuffle(plain)
    for row in plain[: max(TARGET_ROWS - len(chosen), 0)]:
        chosen[row.url] = row
    return sorted(chosen.values(), key=lambda row: (row.outlet, row.url))


def write(rows: list[Row], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as out:
        writer = csv.writer(out)
        writer.writerow(["outlet", "url", "title", *ROOTS, "reviewed", "notes"])
        for row in rows:
            folded = fold(row.title)
            labels = ["?" if root in folded else "0" for root in ROOTS.values()]
            writer.writerow([row.outlet, row.url, row.title, *labels, "no", ""])


def main(argv: list[str]) -> int:
    target = Path(argv[1] if len(argv) > 1 else "tests/matching/fixtures/labeled.csv")
    rng = random.Random(SEED)  # noqa: S311 - reproducible sampling, not security
    with Http() as http:
        titled = collect_titled(http)
        pages = collect_trt_pages(http, rng, skip=set(titled))
    chosen = sample(titled, pages, rng)
    write(chosen, target)
    print(f"wrote {len(chosen)} rows ({len(pages)} TRT page headlines) to {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
