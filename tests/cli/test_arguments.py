"""trnews's arguments (C1, C11) and how it's started (C12)."""

from __future__ import annotations

import argparse
import importlib
import io
import runpy
import sys
from datetime import date

import pytest

from tr_news_scraper import __version__
from tr_news_scraper._cli import (
    ROBOTS_WARNING,
    Console,
    check_requests,
    keywords_from,
    main,
    outlets_from,
    range_from,
)
from tr_news_scraper._files import UsageError

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


def test_importing_the_main_module_runs_nothing(capsys: pytest.CaptureFixture[str]) -> None:
    sys.modules.pop("tr_news_scraper.__main__", None)
    importlib.import_module("tr_news_scraper.__main__")
    assert capsys.readouterr() == ("", "")


def test_help_lists_the_three_commands(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--help"]) == 0
    lines = capsys.readouterr().out.splitlines()
    listed = [line.split()[0] for line in lines if line[:4] == "    " and line[4] != " "]
    assert listed == ["search", "fetch", "coverage"]
    assert main(["fetch", "--help"]) == 0
    assert "--ignore-robots-txt" in capsys.readouterr().out


def test_a_command_is_required(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 2
    assert "the following arguments are required: COMMAND" in capsys.readouterr().err


def test_quiet_and_verbose_exclude_each_other(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["coverage", "-q", "-v"]) == 2
    assert "not allowed with argument" in capsys.readouterr().err


def test_to_is_the_last_day_and_included() -> None:
    assert range_from("2023-02-01", "2023-02-28") == (date(2023, 2, 1), date(2023, 3, 1))
    assert range_from("2023-02-06", "2023-02-06") == (date(2023, 2, 6), date(2023, 2, 7))
    assert range_from(None, None) is None


@pytest.mark.parametrize(
    ("first", "last", "message"),
    [
        ("2023-02-01", None, "give both --from and --to, or neither"),
        (None, "2023-02-01", "give both --from and --to, or neither"),
        (
            "2023-02-30",
            "2023-03-01",
            "--from must be a day as YYYY-MM-DD, such as 2023-02-01, not '2023-02-30'",
        ),
        (
            "2023-02-01",
            "28.02.2023",
            "--to must be a day as YYYY-MM-DD, such as 2023-02-01, not '28.02.2023'",
        ),
        ("2023-02-10", "2023-02-09", "--to (2023-02-09) is before --from (2023-02-10)"),
    ],
)
def test_impossible_ranges_are_usage_errors(
    first: str | None, last: str | None, message: str
) -> None:
    with pytest.raises(UsageError) as error:
        range_from(first, last)
    assert str(error.value) == message


def test_outlets_are_built_in_ids_separated_by_commas() -> None:
    assert outlets_from(None) is None
    assert outlets_from("star, aksam,star,") == ("star", "aksam")


def test_an_unknown_outlet_lists_the_valid_ones() -> None:
    with pytest.raises(UsageError, match="there's no built-in outlet 'hurriyet'; choose from "):
        outlets_from("star,hurriyet")
    with pytest.raises(UsageError, match="--outlets needs at least one outlet id"):
        outlets_from(" , ")


def test_keywords_are_read_as_search_reads_them() -> None:
    assert keywords_from(["deprem", " Deprem ", "tsunami"]) == ("deprem", "tsunami")
    with pytest.raises(UsageError, match="give at least one keyword"):
        keywords_from(["  "])
    with pytest.raises(UsageError, match="too short"):
        keywords_from(["a"])


def namespace(contact: str | None = None, *, ignore: bool = False) -> argparse.Namespace:
    return argparse.Namespace(contact=contact, ignore_robots_txt=ignore)


def test_a_contact_that_would_break_the_user_agent_is_a_usage_error() -> None:
    console = Console(io.StringIO())
    check_requests(namespace("mailto:you@example.org"), console)
    with pytest.raises(UsageError, match="--contact must be printable ASCII"):
        check_requests(namespace("you@example.org; evil"), console)


def test_ignoring_robots_txt_warns_first_even_when_quiet() -> None:
    stream = io.StringIO()
    check_requests(namespace(ignore=True), Console(stream, quiet=True))
    assert stream.getvalue() == ROBOTS_WARNING + "\n"
    assert "permission" in ROBOTS_WARNING
