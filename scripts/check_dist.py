"""Check built distributions before release.

The wheel must hold only the ``tr_news_scraper`` package and its metadata and must declare the
``trnews`` command, and no archive may contain the local planning docs (specs, plans, idea docs).
Usage::

    uv build
    uv run python scripts/check_dist.py dist
"""

from __future__ import annotations

import configparser
import re
import sys
import tarfile
import zipfile
from pathlib import Path

WHEEL_ALLOWED = re.compile(r"^(tr_news_scraper/|tr_news_scraper-[^/]+\.dist-info/)")
PLANNING_DOC = re.compile(r"(^|/)(SPEC[^/]*\.md$|docs/ideas/|docs/intent/|tasks/)")
TRNEWS = "tr_news_scraper._cli:main"


def declares_trnews(wheel: zipfile.ZipFile) -> bool:
    """Whether the wheel's metadata installs the ``trnews`` command."""
    for name in wheel.namelist():
        if not name.endswith(".dist-info/entry_points.txt"):
            continue
        entry_points = configparser.ConfigParser(delimiters=("=",), interpolation=None)
        try:
            entry_points.read_string(wheel.read(name).decode("utf-8"))
        except (configparser.Error, UnicodeDecodeError):
            return False
        return entry_points.get("console_scripts", "trnews", fallback="").strip() == TRNEWS
    return False


def problems(dist: Path) -> list[str]:
    """Return one message per unexpected file in the wheels and sdists under ``dist``."""
    wheels = sorted(dist.glob("*.whl"))
    sdists = sorted(dist.glob("*.tar.gz"))
    if not wheels or not sdists:
        return [f"expected a wheel and an sdist in {dist}"]
    found: list[str] = []
    for wheel in wheels:
        with zipfile.ZipFile(wheel) as archive:
            found += [
                f"{wheel.name}: unexpected file {name}"
                for name in archive.namelist()
                if not WHEEL_ALLOWED.match(name)
            ]
            if not declares_trnews(archive):
                found.append(
                    f"{wheel.name}: no trnews command (console_scripts entry point {TRNEWS})"
                )
    for sdist in sdists:
        with tarfile.open(sdist) as archive:
            found += [
                f"{sdist.name}: planning doc {name}"
                for name in archive.getnames()
                if PLANNING_DOC.search(name)
            ]
    return found


def main(argv: list[str]) -> int:
    """Print the problems found in ``argv[1]`` (default ``dist``); return 1 if there are any."""
    dist = Path(argv[1] if len(argv) > 1 else "dist")
    found = problems(dist)
    for message in found:
        print(message, file=sys.stderr)
    print(f"checked {dist}: {len(found)} problem(s)")
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
