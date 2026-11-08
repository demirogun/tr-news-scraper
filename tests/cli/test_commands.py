"""trnews's commands with stand-ins for the library: options, files and exit codes (C3–C10)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from tr_news_scraper import _cli, coverage
from tr_news_scraper._cli import ROBOTS_WARNING, main
from tr_news_scraper._files import WriteError, read_table
from tr_news_scraper._table import string_series


def checked_coverage() -> pd.DataFrame:
    """coverage(check=True)'s columns, without a request: Milliyet's search is down."""
    table = coverage()
    table["ok"] = pd.Series([True] * 6 + [False], dtype="bool")
    table["problems"] = string_series([""] * 6 + ["the search page answered HTTP 503"])
    table["oldest"] = string_series(["2008-07"] * 6 + [None])
    table["newest"] = string_series(["2026-11"] * 6 + [None])
    table["sample"] = pd.Series([20] * 6 + [0], dtype="int64")
    return table


@pytest.fixture
def checked(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Replace coverage() with a stand-in that records how it was called."""
    calls: list[dict[str, Any]] = []

    def stand_in(**options: Any) -> pd.DataFrame:
        calls.append(options)
        return checked_coverage() if options.get("check") else coverage()

    monkeypatch.setattr(_cli, "coverage", stand_in)
    return calls


def test_coverage_prints_a_table_and_the_notes(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["coverage"]) == 0
    out, err = capsys.readouterr()
    lines = out.splitlines()
    assert lines[0].split() == ["outlet", "name", "method", "earliest", "headlines"]
    assert lines[1].split()[:2] == ["cumhuriyet", "Cumhuriyet"]
    assert sum(line.startswith("  milliyet: ") for line in lines) == 1
    assert "Notes:" in lines
    assert err == ""


def test_coverage_check_adds_the_health_columns(
    checked: list[dict[str, Any]], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["coverage", "--check", "--contact", "mailto:you@example.org"]) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0].split()[-4:] == ["ok", "oldest", "newest", "sample"]
    assert "  milliyet: the search page answered HTTP 503" in out
    assert checked == [
        {"check": True, "contact": "mailto:you@example.org", "obey_robots": True, "cache_dir": None}
    ]


def test_coverage_writes_its_table_to_a_file(
    checked: list[dict[str, Any]], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "outlets.csv"
    assert main(["coverage", "--check", "-o", str(path), "--separator", ";"]) == 0
    out, err = capsys.readouterr()
    assert out == ""
    assert err == f"Wrote {path} (7 outlets).\n"
    table = read_table(path)
    assert table["ok"].tolist() == ["True"] * 6 + ["False"]
    assert path.read_text(encoding="utf-8-sig").startswith("outlet;name;method;")
    assert not (tmp_path / "outlets.report.json").exists()


def test_coverage_never_overwrites_without_overwrite(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "outlets.jsonl"
    path.write_text("keep me\n", encoding="utf-8")
    assert main(["coverage", "-o", str(path)]) == 2
    assert "already exists; add --overwrite" in capsys.readouterr().err
    assert path.read_text(encoding="utf-8") == "keep me\n"
    assert main(["coverage", "-o", str(path), "--overwrite", "-q"]) == 0
    assert capsys.readouterr().err == ""
    assert len(path.read_text(encoding="utf-8").splitlines()) == 7


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (
            ["-o", "outlets.xlsx"],
            "outlets.xlsx: the file name must end in .csv, .jsonl or .parquet",
        ),
        (["--separator", ";"], "--separator applies only to .csv files"),
        (["-o", "outlets.jsonl", "--separator", ";"], "--separator applies only to .csv files"),
        (["--check", "--contact", "a;b"], "--contact must be printable ASCII"),
    ],
)
def test_coverage_usage_mistakes_exit_with_2(
    checked: list[dict[str, Any]],
    argv: list[str],
    message: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["coverage", *argv]) == 2
    assert f"trnews coverage: error: {message}" in capsys.readouterr().err
    assert checked == []


def test_coverage_check_warns_before_ignoring_robots_txt(
    checked: list[dict[str, Any]], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["coverage", "--check", "--ignore-robots-txt"]) == 0
    assert capsys.readouterr().err.startswith(ROBOTS_WARNING)
    assert checked[0]["obey_robots"] is False


def test_a_file_that_cant_be_written_exits_with_1(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail(*args: Any, **kwargs: Any) -> None:
        raise WriteError(f"couldn't write {tmp_path / 'outlets.csv'}: Access is denied")

    monkeypatch.setattr(_cli, "save", fail)
    assert main(["coverage", "-o", str(tmp_path / "outlets.csv")]) == 1
    assert capsys.readouterr().err == (
        f"trnews coverage: couldn't write {tmp_path / 'outlets.csv'}: Access is denied\n"
    )
