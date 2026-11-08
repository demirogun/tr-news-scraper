"""On-disk cache of successful responses, so repeated searches don't refetch.

Each entry is two files under ``<cache_dir>/v1/<first two key characters>/``: the body, then a
JSON metadata file written last, which marks the entry complete. Both are written to a temporary
file and moved into place, so a crash never leaves a half-written entry that looks valid.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from platformdirs import user_cache_dir

from tr_news_scraper._http.clock import Clock

logger = logging.getLogger("tr_news_scraper.http")

APP_NAME = "tr-news-scraper"
_LAYOUT = "v1"
_KEPT_HEADERS = frozenset({"content-type", "content-language", "last-modified", "etag"})
_REPLACE_ATTEMPTS = 5


@dataclass(frozen=True, slots=True)
class CachePolicy:
    """How one request may use the cache.

    ``ttl``: serve a cached copy younger than this; ``None`` always fetches (and still stores).
    ``offline``: serve only from the cache, whatever its age; a miss raises ``NotCached``.
    ``no_store``: don't write the response to the cache.
    """

    ttl: timedelta | None = None
    offline: bool = False
    no_store: bool = False


@dataclass(frozen=True, slots=True)
class CachedEntry:
    url: str
    status: int
    headers: Mapping[str, str]
    content: bytes
    fetched_at: datetime


class DiskCache:
    """Stores 200 responses on disk and trims itself to a size limit, oldest entries first."""

    def __init__(self, root: Path | None, max_bytes: int, clock: Clock) -> None:
        base = root if root is not None else Path(user_cache_dir(APP_NAME))
        self._root = base / _LAYOUT
        self._max_bytes = max_bytes
        self._clock = clock

    @staticmethod
    def key(url: str, accept: str) -> str:
        return hashlib.sha256(f"{accept}\n{url}".encode()).hexdigest()

    def load(self, key: str, *, ttl: timedelta | None, any_age: bool = False) -> CachedEntry | None:
        """Return the entry for ``key`` if it exists and is fresh enough, else ``None``."""
        meta_path, body_path = self._paths(key)
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            content = body_path.read_bytes()
            fetched_at = datetime.fromisoformat(meta["fetched_at"])
            entry = CachedEntry(
                meta["url"], int(meta["status"]), dict(meta["headers"]), content, fetched_at
            )
        except (OSError, ValueError, KeyError, TypeError):
            return None
        if any_age:
            return entry
        if ttl is None or self._clock.now() - fetched_at > ttl:
            return None
        return entry

    def store(self, key: str, entry: CachedEntry) -> None:
        """Write ``entry``. A failure is logged, never raised: the cache is only an optimization."""
        meta_path, body_path = self._paths(key)
        meta = {
            "url": entry.url,
            "status": entry.status,
            "headers": {k: v for k, v in entry.headers.items() if k in _KEPT_HEADERS},
            "fetched_at": entry.fetched_at.isoformat(),
        }
        try:
            body_path.parent.mkdir(parents=True, exist_ok=True)
            self._write_atomically(body_path, entry.content)
            self._write_atomically(meta_path, json.dumps(meta).encode())
        except OSError as error:
            logger.warning("could not cache %s: %s", entry.url, error)

    def prune(self) -> None:
        """Remove incomplete entries, then the oldest ones until the cache fits its limit."""
        if not self._root.exists():
            return
        entries: list[tuple[str, int, Path, Path]] = []
        total = 0
        for meta_path in self._root.glob("*/*.json"):
            body_path = meta_path.with_suffix(".body")
            try:
                fetched_at = str(json.loads(meta_path.read_text(encoding="utf-8"))["fetched_at"])
                size = meta_path.stat().st_size + body_path.stat().st_size
            except (OSError, ValueError, KeyError, TypeError):
                _remove(meta_path, body_path)
                continue
            entries.append((fetched_at, size, meta_path, body_path))
            total += size
        for body_path in self._root.glob("*/*.body"):
            if not body_path.with_suffix(".json").exists():
                _remove(body_path)
        for _fetched_at, size, meta_path, body_path in sorted(entries):
            if total <= self._max_bytes:
                break
            _remove(meta_path, body_path)
            total -= size

    def _paths(self, key: str) -> tuple[Path, Path]:
        folder = self._root / key[:2]
        return folder / f"{key}.json", folder / f"{key}.body"

    def _write_atomically(self, path: Path, data: bytes) -> None:
        handle, temp_name = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
        try:
            with os.fdopen(handle, "wb") as temp:
                temp.write(data)
            for attempt in range(1, _REPLACE_ATTEMPTS + 1):
                try:
                    os.replace(temp_name, path)
                    return
                except PermissionError:
                    # Windows briefly locks a file another process (or a virus scanner) has open.
                    if attempt == _REPLACE_ATTEMPTS:
                        raise
                    self._clock.sleep(0.05 * attempt)
        finally:
            if os.path.exists(temp_name):
                os.remove(temp_name)


def _remove(*paths: Path) -> None:
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError as error:
            logger.warning("could not remove cache file %s: %s", path, error)
