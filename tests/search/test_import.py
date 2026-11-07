"""Importing the package stays light: pandas waits until a table is built (S11)."""

from __future__ import annotations

import subprocess
import sys


def test_importing_the_package_leaves_pandas_unimported() -> None:
    code = (
        "import sys, tr_news_scraper, tr_news_scraper.matching, tr_news_scraper.outlets; "
        "print('pandas' in sys.modules)"
    )
    finished = subprocess.run(  # noqa: S603 - the test's own interpreter and a fixed script
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert finished.stdout.strip() == "False"
