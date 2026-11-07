"""Package-level behavior: version, the 0.1.0 migration message, public surface, logging."""

from __future__ import annotations

import ast
import importlib
import logging
import re
from importlib.metadata import version
from pathlib import Path

import pytest
import requests
from requests_mock.exceptions import NoMockAddress

import tr_news_scraper
from tr_news_scraper.errors import TrNewsError

CHANGELOG = Path(__file__).resolve().parents[1] / "CHANGELOG.md"


def test_version_comes_from_package_metadata() -> None:
    assert tr_news_scraper.__version__ == version("tr-news-scraper")


def test_old_import_path_explains_the_migration() -> None:
    with pytest.raises(ImportError, match=r"search, fetch.*'Migrating from 0\.1\.0'"):
        importlib.import_module("tr_news_scraper.tr_news_scraper")


def test_changelog_has_the_migration_section_the_error_points_to() -> None:
    headings = re.findall(r"(?m)^#+ (.+?)\s*$", CHANGELOG.read_text(encoding="utf-8"))
    assert "Migrating from 0.1.0" in headings


def test_the_public_api_is_search_fetch_coverage_and_their_results() -> None:
    assert sorted(tr_news_scraper.__all__) == [
        "FetchResult",
        "SearchResult",
        "__version__",
        "coverage",
        "fetch",
        "search",
    ]


def test_package_logger_stays_silent_unless_the_application_configures_logging() -> None:
    handlers = logging.getLogger("tr_news_scraper").handlers
    assert any(isinstance(handler, logging.NullHandler) for handler in handlers)


def test_library_errors_share_one_base_class() -> None:
    assert issubclass(TrNewsError, Exception)


def test_only_the_http_layer_imports_requests() -> None:
    package = Path(tr_news_scraper.__file__).parent
    importers = []
    for module in package.rglob("*.py"):
        if "_http" in module.relative_to(package).parts:
            continue
        for node in ast.walk(ast.parse(module.read_text(encoding="utf-8"))):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            if any(name == "requests" or name.startswith("requests.") for name in names):
                importers.append(module.relative_to(package).as_posix())
    assert importers == []


def test_unit_tests_cannot_reach_the_real_network() -> None:
    with pytest.raises(NoMockAddress):
        requests.get("https://example.com/", timeout=5)
