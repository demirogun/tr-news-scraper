"""Package-level behavior: version, the 0.1.0 migration message, public surface, logging."""

from __future__ import annotations

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


def test_public_api_is_empty_until_search_and_fetch_exist() -> None:
    assert tr_news_scraper.__all__ == []


def test_package_logger_stays_silent_unless_the_application_configures_logging() -> None:
    handlers = logging.getLogger("tr_news_scraper").handlers
    assert any(isinstance(handler, logging.NullHandler) for handler in handlers)


def test_library_errors_share_one_base_class() -> None:
    assert issubclass(TrNewsError, Exception)


def test_unit_tests_cannot_reach_the_real_network() -> None:
    with pytest.raises(NoMockAddress):
        requests.get("https://example.com/", timeout=5)
