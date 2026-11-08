"""trnews's commands with stand-ins for the library: options, files and exit codes (C3–C10)."""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from tests.cli.conftest import (
    HAS_PYARROW,
    Library,
    fetch_result,
    fetched_table,
    search_result,
)
from tr_news_scraper import FetchResult, SearchResult, _cli, coverage
from tr_news_scraper._cli import ROBOTS_WARNING, main
from tr_news_scraper._files import WriteError, read_table
from tr_news_scraper._table import string_series
from tr_news_scraper.errors import FetchFailed, SearchFailed


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


SEARCH = ["search", "deprem", "tsunami", "--from", "2023-02-01", "--to", "2023-02-28"]
FORMATS = [
    ".csv",
    ".jsonl",
    pytest.param(
        ".parquet", marks=pytest.mark.skipif(not HAS_PYARROW, reason="needs the parquet extra")
    ),
]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def test_search_writes_the_articles_and_the_report(
    library: Library, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "found.csv"
    assert main([*SEARCH, "-o", str(path)]) == 0
    assert len(read_table(path)) == 3
    report = read_json(tmp_path / "found.report.json")
    assert (report["command"], report["fetch"]) == ("search", None)
    assert not (tmp_path / "found.outside.csv").exists()
    err = capsys.readouterr().err
    assert err.startswith("Searching 7 outlets for deprem, tsunami, 2023-02-01 to 2023-02-28 ...\n")
    assert f"\n{search_result()}\n" in err
    assert err.endswith(f"Wrote {path} (3 rows) and {tmp_path / 'found.report.json'}.\n")


def test_search_passes_its_options_to_the_library(library: Library, tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    contact = "mailto:you@example.org"
    library.on_search = lambda: search_result(f"a site echoed the User-Agent ({contact})")
    argv = [
        *SEARCH,
        *("-o", str(tmp_path / "found.jsonl"), "--outlets", "star,aksam", "--offline"),
        *("--contact", contact, "--cache-dir", str(cache), "--ignore-robots-txt", "-q"),
    ]
    assert main(argv) == 0
    assert library.searches == [
        {
            "keywords": ("deprem", "tsunami"),
            "start": date(2023, 2, 1),
            "end": date(2023, 3, 1),
            "outlets": ("star", "aksam"),
            "contact": contact,
            "obey_robots": False,
            "offline": True,
            "cache_dir": cache,
        }
    ]
    assert library.fetches == []
    report = read_json(tmp_path / "found.report.json")
    assert report["options"] == {
        "outlets": ["star", "aksam"],
        "fetch": False,
        "obey_robots": False,
        "offline": True,
        "refresh": False,
    }
    assert contact not in (tmp_path / "found.report.json").read_text(encoding="utf-8")


def test_search_fetch_adds_fetch_columns_and_the_outside_rows(
    library: Library, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "found.csv"
    assert main([*SEARCH, "--fetch", "--refresh", "-o", str(path)]) == 0
    assert list(read_table(path).columns) == list(fetched_table().columns)
    assert len(read_table(path)) == 2
    assert len(read_table(tmp_path / "found.outside.csv")) == 1
    [call] = library.fetches
    assert isinstance(call["articles"], SearchResult)
    assert (call["refresh"], call["obey_robots"], call["offline"]) == (True, True, False)
    report = read_json(tmp_path / "found.report.json")
    assert report["files"]["outside"] == {"file": "found.outside.csv", "rows": 1}
    assert [row["failed"] for row in report["fetch"]["report"]] == [0, 1, 0]
    err = capsys.readouterr().err
    assert "\nReading 3 articles ...\n" in err
    assert f"\n{fetch_result()}\n" in err
    assert err.endswith(
        f"Wrote {path} (2 rows), {tmp_path / 'found.outside.csv'} (1 row) and "
        f"{tmp_path / 'found.report.json'}.\n"
    )


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["search", "a", "--from", "2023-02-01", "--to", "2023-02-28"], "too short"),
        (["search", "deprem", "--from", "2023-02-30", "--to", "2023-03-01"], "--from must be"),
        (
            ["search", "deprem", "--from", "2023-03-01", "--to", "2023-02-01"],
            "--to (2023-02-01) is before --from (2023-03-01)",
        ),
        ([*SEARCH, "--outlets", "hurriyet"], "there's no built-in outlet 'hurriyet'; choose"),
        ([*SEARCH, "--refresh"], "--refresh applies only with --fetch"),
    ],
)
def test_search_usage_mistakes_exit_with_2_before_any_request(
    library: Library,
    tmp_path: Path,
    argv: list[str],
    message: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main([*argv, "-o", str(tmp_path / "found.csv")]) == 2
    assert message in capsys.readouterr().err
    assert library.searches == []


def test_an_existing_outside_file_stops_the_search_before_any_request(
    library: Library, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "found.outside.csv").write_text("old", encoding="utf-8")
    assert main([*SEARCH, "-o", str(tmp_path / "found.csv")]) == 2
    assert "found.outside.csv already exists; add --overwrite" in capsys.readouterr().err
    assert library.searches == []


def test_overwrite_removes_an_outside_file_the_new_run_doesnt_write(
    library: Library, tmp_path: Path
) -> None:
    path = tmp_path / "found.csv"
    assert main([*SEARCH, "--fetch", "-q", "-o", str(path)]) == 0
    assert (tmp_path / "found.outside.csv").exists()
    assert main([*SEARCH, "-q", "--overwrite", "-o", str(path)]) == 0
    assert not (tmp_path / "found.outside.csv").exists()
    assert len(read_table(path)) == 3


@pytest.mark.parametrize("fetching", [False, True])
def test_failures_exit_with_1_and_write_nothing(
    library: Library, tmp_path: Path, capsys: pytest.CaptureFixture[str], fetching: bool
) -> None:
    def search_fails() -> SearchResult:
        raise SearchFailed({"star": "HTTP 503"})

    def fetch_fails(progress: Any) -> FetchResult:
        raise FetchFailed({"star": "HTTP 404"})

    if fetching:
        library.on_fetch = fetch_fails
    else:
        library.on_search = search_fails
    argv = [*SEARCH, "-q", "-o", str(tmp_path / "found.csv"), *(["--fetch"] if fetching else [])]
    assert main(argv) == 1
    expected = (
        "trnews search: no article could be read:\n  star: HTTP 404\n"
        if fetching
        else "trnews search: every outlet failed:\n  star: HTTP 503\n"
    )
    assert capsys.readouterr().err == expected
    assert list(tmp_path.iterdir()) == []


def test_ctrl_c_while_fetching_says_how_to_continue(
    library: Library, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def stopped(progress: Any) -> FetchResult:
        progress("aksam", 1, 1)
        progress("star", 1, 1)
        raise KeyboardInterrupt

    library.on_fetch = stopped
    assert main([*SEARCH, "--fetch", "-q", "-o", str(tmp_path / "found.csv")]) == 130
    assert capsys.readouterr().err == (
        "Stopped after 2 of 3 articles; no file was written.\n"
        "The articles read are saved in the cache: run the same command again to continue.\n"
    )
    assert list(tmp_path.iterdir()) == []


def test_ctrl_c_while_searching_exits_with_130(
    library: Library, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def stopped() -> SearchResult:
        raise KeyboardInterrupt

    library.on_search = stopped
    assert main([*SEARCH, "-q", "-o", str(tmp_path / "found.csv")]) == 130
    assert capsys.readouterr().err == "Stopped while searching; no file was written.\n"


def test_quiet_leaves_only_errors(
    library: Library, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def noisy() -> SearchResult:
        logging.getLogger("tr_news_scraper.search").warning("Sözcü failed: HTTP 503")
        logging.getLogger("tr_news_scraper.search").info("Star: 3 matching articles")
        return search_result()

    library.on_search = noisy
    assert main([*SEARCH, "-q", "-o", str(tmp_path / "found.csv")]) == 0
    assert capsys.readouterr() == ("", "")
    assert main([*SEARCH, "--overwrite", "-o", str(tmp_path / "found.csv")]) == 0
    err = capsys.readouterr().err
    assert "\n  warning: Sözcü failed: HTTP 503\n  Star: 3 matching articles\n" in err


def searched(library: Library, tmp_path: Path, name: str = "found.csv") -> Path:
    """The table and report file trnews search writes, through the stand-in."""
    path = tmp_path / name
    assert main([*SEARCH, "-q", "-o", str(path)]) == 0
    library.searches.clear()
    return path


@pytest.mark.parametrize("suffix", FORMATS)
def test_fetch_reads_a_table_and_reuses_its_report(
    library: Library, tmp_path: Path, capsys: pytest.CaptureFixture[str], suffix: str
) -> None:
    found = searched(library, tmp_path, f"found{suffix}")
    output = tmp_path / "fetched.jsonl"
    assert main(["fetch", str(found), "-o", str(output)]) == 0
    [call] = library.fetches
    pd.testing.assert_frame_equal(call["articles"], read_table(found))
    assert (call["keywords"], call["start"], call["end"]) == (
        ("deprem", "tsunami"),
        date(2023, 2, 1),
        date(2023, 3, 1),
    )
    report = read_json(tmp_path / "fetched.report.json")
    assert (report["command"], report["input"]) == ("fetch", found.name)
    assert report["search"] == read_json(tmp_path / "found.report.json")["search"]
    assert (report["from"], report["to"]) == ("2023-02-01", "2023-02-28")
    assert len(read_table(output)) == 2
    assert len(read_table(tmp_path / "fetched.outside.jsonl")) == 1
    assert capsys.readouterr().err.startswith("Reading 3 articles ...\n")


def test_fetch_options_win_over_the_report(library: Library, tmp_path: Path) -> None:
    found = searched(library, tmp_path)
    argv = ["fetch", str(found), "-q", "-o", str(tmp_path / "fetched.csv")]
    assert main([*argv, "--from", "2023-02-06", "--to", "2023-02-06"]) == 0
    [call] = library.fetches
    assert (call["keywords"], call["start"], call["end"]) == (
        ("deprem", "tsunami"),
        date(2023, 2, 6),
        date(2023, 2, 7),
    )


def test_fetch_without_a_report_has_no_keywords_or_range(library: Library, tmp_path: Path) -> None:
    table = tmp_path / "picked.csv"
    table.write_text("outlet,url\nstar,https://www.star.com.tr/guncel/a\n", encoding="utf-8")
    assert main(["fetch", str(table), "-q", "-o", str(tmp_path / "fetched.csv")]) == 0
    [call] = library.fetches
    assert (call["keywords"], call["start"], call["end"]) == (None, None, None)
    report = read_json(tmp_path / "fetched.report.json")
    assert (report["search"], report["searched_at"], report["input"]) == (None, None, "picked.csv")


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (
            "outlet,link\nstar,https://x/1\n",
            "needs the columns outlet and url; it has: outlet, link",
        ),
        ("outlet,url\nstar,https://x/1\nstar,\n", "row 2 has no outlet or no url"),
        (
            "outlet,url\nhurriyet,https://x/1\n",
            "there's no built-in outlet 'hurriyet'; choose from",
        ),
    ],
)
def test_a_table_fetch_cant_use_is_a_usage_error(
    library: Library,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    content: str,
    message: str,
) -> None:
    table = tmp_path / "picked.csv"
    table.write_text(content, encoding="utf-8")
    assert main(["fetch", str(table), "-o", str(tmp_path / "fetched.csv")]) == 2
    assert message in capsys.readouterr().err
    assert library.fetches == []


@pytest.mark.parametrize(
    ("report", "message"),
    [
        ('{"keywords": "deprem"}', "keywords must be a list of words"),
        ('{"keywords": ["a"]}', "too short"),
        ('{"from": "2023-02-01", "to": null}', "records the range '2023-02-01' to None"),
        ('{"from": "2023-03-01", "to": "2023-02-01"}', "which isn't valid"),
        ("[]", "isn't a trnews report file"),
    ],
)
def test_a_damaged_report_file_is_a_usage_error(
    library: Library,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    report: str,
    message: str,
) -> None:
    table = tmp_path / "picked.csv"
    table.write_text("outlet,url\nstar,https://x/1\n", encoding="utf-8")
    (tmp_path / "picked.report.json").write_text(report, encoding="utf-8")
    assert main(["fetch", str(table), "-o", str(tmp_path / "fetched.csv")]) == 2
    assert message in capsys.readouterr().err
    assert library.fetches == []


def test_fetch_of_a_missing_file_or_half_a_range_is_a_usage_error(
    library: Library, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = ["-o", str(tmp_path / "fetched.csv")]
    assert main(["fetch", str(tmp_path / "nowhere.csv"), *output]) == 2
    assert "nowhere.csv doesn't exist" in capsys.readouterr().err
    found = searched(library, tmp_path)
    assert main(["fetch", str(found), *output, "--from", "2023-02-01"]) == 2
    assert "give both --from and --to, or neither" in capsys.readouterr().err
    assert library.fetches == []


def test_a_report_with_keywords_and_no_range_gives_the_keywords(
    library: Library, tmp_path: Path
) -> None:
    table = tmp_path / "picked.csv"
    table.write_text("outlet,url\nstar,https://x/1\n", encoding="utf-8")
    (tmp_path / "picked.report.json").write_text('{"keywords": ["Deprem"]}', encoding="utf-8")
    assert main(["fetch", str(table), "-q", "-o", str(tmp_path / "fetched.csv")]) == 0
    [call] = library.fetches
    assert (call["keywords"], call["start"], call["end"]) == (("Deprem",), None, None)


def test_ctrl_c_while_writing_exits_with_130(
    library: Library,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def stopped(*args: Any, **kwargs: Any) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(_cli, "save", stopped)
    assert main([*SEARCH, "-q", "-o", str(tmp_path / "found.csv")]) == 130
    assert capsys.readouterr().err == "Stopped.\n"


def test_ctrl_c_in_fetch_says_how_to_continue(
    library: Library, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def stopped(progress: Any) -> FetchResult:
        progress("star", 1, 1)
        raise KeyboardInterrupt

    found = searched(library, tmp_path)
    library.on_fetch = stopped
    assert main(["fetch", str(found), "-q", "-o", str(tmp_path / "fetched.csv")]) == 130
    assert capsys.readouterr().err.startswith("Stopped after 1 of 3 articles; no file was written.")
    assert not (tmp_path / "fetched.csv").exists()
