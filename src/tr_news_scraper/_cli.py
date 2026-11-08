"""trnews: search Turkish news archives and read the articles from the command line (internal)."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from tr_news_scraper._version import __version__


def build_parser() -> argparse.ArgumentParser:
    """trnews's arguments."""
    parser = argparse.ArgumentParser(
        prog="trnews",
        description="Search Turkish news archives by keyword and date range; read the articles.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s (tr-news-scraper) {__version__}"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run ``trnews`` with ``argv`` (default: the command line) and return its exit code."""
    parser = build_parser()
    try:
        parser.parse_args(argv)
    except SystemExit as stop:  # --help, --version and usage mistakes
        return stop.code if isinstance(stop.code, int) else 0
    return 0
