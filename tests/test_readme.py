"""README.md agrees with the code it describes, and works on PyPI as on GitHub (release, R6)."""

from __future__ import annotations

import os
import re
import shlex
import sys
from pathlib import Path

import pytest
from platformdirs import user_cache_dir

from tr_news_scraper import __version__, coverage
from tr_news_scraper._cli import build_parser
from tr_news_scraper._fetched import ADDED_COLUMNS
from tr_news_scraper._files import cells
from tr_news_scraper._http import HttpConfig
from tr_news_scraper._table import ARTICLE_COLUMNS

README = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
SECTIONS = [
    "Türkçe özet",
    "Install",
    "Quick start",
    "What you get",
    "Outlets",
    "Responsible use",
    "Limits",
    "Citing",
    "Migrating from 0.1.0",
    "Development",
    "License",
]
OUTLET_HEADER = "| Outlet | `id` | Archive | From | Headlines |"
CACHE_FOLDERS = {
    "win32": r"%LOCALAPPDATA%\tr-news-scraper\tr-news-scraper\Cache",
    "darwin": "~/Library/Caches/tr-news-scraper",
    "linux": "~/.cache/tr-news-scraper",
}


def blocks(language: str) -> list[str]:
    return re.findall(rf"^```{language}\n(.*?)^```$", README, re.MULTILINE | re.DOTALL)


def trnews_lines() -> list[str]:
    return [
        line for block in blocks("bash") for line in block.splitlines() if line[:7] == "trnews "
    ]


def test_it_has_the_sections_of_the_outline_in_order() -> None:
    assert re.findall(r"^## (.+)$", README, re.MULTILINE) == SECTIONS


def test_the_outlet_table_matches_coverage() -> None:
    lines = README.splitlines()
    start = lines.index(OUTLET_HEADER) + 2
    rows = []
    for line in lines[start:]:
        if not line.startswith("|"):
            break
        rows.append([cell.strip().strip("`") for cell in line.strip("|").split("|")])
    table = coverage()
    columns = [cells(table[name]) for name in ("name", "outlet", "method", "earliest", "headlines")]
    expected = [[value or "—" for value in row] for row in zip(*columns, strict=True)]
    assert rows == expected


def test_each_outlets_notes_are_the_ones_coverage_gives() -> None:
    table = coverage()
    for name, notes in zip(table["name"], table["notes"], strict=True):
        assert f"- **{name}:** {notes}\n" in README


def test_every_column_of_both_tables_is_described() -> None:
    for column in (*ARTICLE_COLUMNS, *ADDED_COLUMNS):
        assert f"| `{column}` |" in README


@pytest.mark.parametrize("line", trnews_lines())
def test_every_trnews_example_parses(line: str) -> None:
    build_parser().parse_args(shlex.split(line)[1:])


def test_there_are_trnews_examples_for_every_command() -> None:
    commands = {line.split()[1] for line in trnews_lines()}
    assert commands == {"search", "fetch", "coverage"}


def test_every_python_example_compiles() -> None:
    examples = blocks("python")
    assert len(examples) >= 2
    for example in examples:
        compile(example, "README.md", "exec")


def test_every_link_is_absolute_because_pypi_shows_the_same_file() -> None:
    targets = re.findall(r"\]\(([^)\s]+)\)", README)
    assert targets
    assert [target for target in targets if not target.startswith("https://")] == []


def test_the_user_agent_is_the_one_sent() -> None:
    agent = HttpConfig().user_agent.replace(__version__, "<version>")
    assert f"`{agent}`" in README.replace("\n  ", " ")


@pytest.mark.skipif(sys.platform not in CACHE_FOLDERS, reason="no documented cache folder")
def test_the_cache_folder_is_where_the_readme_says(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    shown = CACHE_FOLDERS[sys.platform]
    assert f"`{shown}`" in README
    assert user_cache_dir("tr-news-scraper") == os.path.expanduser(os.path.expandvars(shown))
