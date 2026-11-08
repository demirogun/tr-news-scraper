"""trnews's arguments (C1) and how it's started (C12)."""

from __future__ import annotations

import runpy
import sys

import pytest

from tr_news_scraper import __version__
from tr_news_scraper._cli import main

VERSION = f"trnews (tr-news-scraper) {__version__}"


def test_version_names_the_tool_and_its_version(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == VERSION


def test_python_dash_m_runs_trnews(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["tr_news_scraper", "--version"])
    with pytest.raises(SystemExit) as stop:
        runpy.run_module("tr_news_scraper", run_name="__main__", alter_sys=True)
    assert stop.value.code == 0
    assert capsys.readouterr().out.strip() == VERSION
