"""F4: trafilatura and htmldate only ever get HTML that Http downloaded; nothing in the package
reaches trafilatura's own network code."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import tr_news_scraper
from tr_news_scraper._extract import extract

FIXTURES = Path(__file__).parent / "fixtures"
NETWORK_NAMES = {"fetch_url", "fetch_response", "load_html_from_url", "add_to_compressed_dict"}
NETWORK_MODULES = ("trafilatura.downloads", "trafilatura.spider", "trafilatura.feeds")


def test_no_module_in_the_package_touches_trafilaturas_network_code() -> None:
    package = Path(tr_news_scraper.__file__).parent
    found = []
    for module in package.rglob("*.py"):
        for node in ast.walk(ast.parse(module.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(NETWORK_MODULES):
                found.append(f"{module.name}: from {node.module}")
            if isinstance(node, ast.Import):
                found += [
                    f"{module.name}: import {alias.name}"
                    for alias in node.names
                    if alias.name.startswith(NETWORK_MODULES)
                ]
            if isinstance(node, ast.Name | ast.Attribute):
                name = node.id if isinstance(node, ast.Name) else node.attr
                if name in NETWORK_NAMES:
                    found.append(f"{module.name}: {name}")
    assert found == []


def test_extraction_never_calls_trafilaturas_downloader(monkeypatch: pytest.MonkeyPatch) -> None:
    import trafilatura.downloads

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("trafilatura tried to download something")

    for name in ("fetch_url", "fetch_response"):
        monkeypatch.setattr(trafilatura.downloads, name, refuse)
    for page in sorted(FIXTURES.glob("*/page.html")):
        found = extract(page.read_text(encoding="utf-8"), "https://www.example.com.tr/a")
        assert found.error is None, page.parent.name
