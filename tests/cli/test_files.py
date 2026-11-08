"""trnews's files: formats, types, paths, the overwrite check and the report file (C2–C6)."""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from tests.cli.conftest import HAS_PYARROW, fetch_result, fetched_table, search_result
from tr_news_scraper import _files
from tr_news_scraper._files import (
    PARQUET_HINT,
    UsageError,
    WriteError,
    check_writable,
    make_report,
    outputs_for,
    read_report,
    read_table,
    save,
)
from tr_news_scraper._table import DAY_DTYPE, TIME_DTYPE

FORMATS = [
    ".csv",
    ".jsonl",
    pytest.param(
        ".parquet", marks=pytest.mark.skipif(not HAS_PYARROW, reason="needs the parquet extra")
    ),
]
BOM = b"\xef\xbb\xbf"


def write(frame: pd.DataFrame, path: Path, separator: str = ",") -> Path:
    save({path: frame}, separator=separator)
    return path


@pytest.mark.parametrize("separator", [",", ";"])
def test_csv_starts_with_a_byte_order_mark_and_uses_the_separator(
    tmp_path: Path, separator: str
) -> None:
    raw = write(fetched_table(), tmp_path / "a.csv", separator).read_bytes()
    assert raw.startswith(BOM)
    header = raw[len(BOM) :].split(b"\r\n", 1)[0].decode("utf-8")
    assert header.split(separator) == list(fetched_table().columns)


def test_csv_quotes_text_with_line_breaks(tmp_path: Path) -> None:
    text = write(fetched_table(), tmp_path / "a.csv").read_text(encoding="utf-8-sig")
    assert '"Birinci satır, virgüllü.\nİkinci satır; noktalı virgüllü ve ""tırnaklı""."' in text


def test_jsonl_writes_iso_times_days_and_nulls(tmp_path: Path) -> None:
    lines = write(fetched_table(), tmp_path / "a.jsonl").read_text(encoding="utf-8").splitlines()
    first, second = json.loads(lines[0]), json.loads(lines[1])
    assert len(lines) == 3
    assert first["day"] == "2023-02-06"
    assert first["lastmod"] == "2023-02-06T04:17:00+03:00"
    assert first["fetched_at"] == "2026-11-08T14:03:12.345678+03:00"
    assert first["copy_group"] == 1
    assert first["title"] == "Akşam'da deprem"
    assert second["day"] is None
    assert second["author"] is None
    assert second["text_matched"] == ""


def test_csv_writes_iso_times_days_and_empty_cells(tmp_path: Path) -> None:
    path = write(fetched_table(), tmp_path / "a.csv")
    rows = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    assert rows.loc[0, "day"] == "2023-02-06"
    assert rows.loc[0, "published"] == "2023-02-06T04:02:00+03:00"
    assert rows.loc[1, "day"] == ""
    assert rows.loc[1, "error"] == "HTTP 404"


@pytest.mark.parametrize("suffix", FORMATS)
def test_every_format_round_trips_with_its_types(tmp_path: Path, suffix: str) -> None:
    table = fetched_table()
    found = read_table(write(table, tmp_path / f"a{suffix}"))
    pd.testing.assert_frame_equal(found, table)
    assert found["day"].dtype == DAY_DTYPE
    assert found["published"].dtype == TIME_DTYPE


def test_csv_cells_a_spreadsheet_would_run_start_with_an_apostrophe(tmp_path: Path) -> None:
    text = write(fetched_table(), tmp_path / "a.csv").read_text(encoding="utf-8-sig")
    assert """'=HYPERLINK(""http://x"", ""x"")""" in text
    assert ",''=x," in text
    assert ",'-15 derece," in text
    assert "Akşam'da deprem" in text


def test_jsonl_keeps_formula_like_cells_as_they_are(tmp_path: Path) -> None:
    lines = write(fetched_table(), tmp_path / "a.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[2])["text"] == "-15 derece"


def test_reading_restores_types_in_a_table_written_by_hand(tmp_path: Path) -> None:
    path = tmp_path / "hand.csv"
    path.write_text(
        "outlet;url;day;title\n"
        "star;https://www.star.com.tr/guncel/a;2023-02-07;Başlık\n"
        "aksam;https://www.aksam.com.tr/guncel/b/haber-2;;\n",
        encoding="utf-8",
    )
    table = read_table(path)
    assert list(table.columns) == ["outlet", "url", "day", "title"]
    assert table["day"].dtype == DAY_DTYPE
    assert table["day"].tolist()[0] == pd.Timestamp("2023-02-07")
    assert table["outlet"].dtype == "string"
    assert table["title"].isna().tolist() == [False, True]


@pytest.mark.parametrize(
    ("column", "value", "expected"),
    [
        ("day", "12.02.2023", "a day such as 2023-02-12"),
        ("published", "dün", "a time such as 2023-02-12T06:02:00+03:00"),
        ("copy_group", "1.5", "a whole number"),
    ],
)
def test_a_value_of_the_wrong_kind_names_its_row(
    tmp_path: Path, column: str, value: str, expected: str
) -> None:
    path = tmp_path / "bad.csv"
    path.write_text(
        f"outlet,url,{column}\nstar,https://x/1,\nstar,https://x/2,{value}\n", encoding="utf-8"
    )
    with pytest.raises(UsageError) as error:
        read_table(path)
    assert str(error.value) == f"{path}: row 2's {column} is '{value}', not {expected}"


def test_a_csv_in_another_encoding_says_how_to_save_it(tmp_path: Path) -> None:
    path = tmp_path / "excel.csv"
    path.write_bytes("outlet;url;title\nstar;https://x/1;Akşam\n".encode("cp1254"))
    with pytest.raises(UsageError, match="save it as 'CSV UTF-8'"):
        read_table(path)


def test_a_jsonl_line_that_isnt_an_object_names_its_line(tmp_path: Path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text('{"outlet": "star", "url": "https://x/1"}\n\n[1, 2]\n', encoding="utf-8")
    with pytest.raises(UsageError, match="line 3 isn't a JSON object"):
        read_table(path)
    path.write_text('{"outlet": "star",\n', encoding="utf-8")
    with pytest.raises(UsageError, match="line 1 isn't JSON"):
        read_table(path)


def test_an_empty_jsonl_file_is_an_empty_articles_table(tmp_path: Path) -> None:
    path = tmp_path / "empty.jsonl"
    path.write_text("", encoding="utf-8")
    table = read_table(path)
    assert len(table) == 0
    assert {"outlet", "url", "day"} <= set(table.columns)
    assert table["day"].dtype == DAY_DTYPE


def test_reading_a_missing_file_is_a_usage_error(tmp_path: Path) -> None:
    with pytest.raises(UsageError, match="doesn't exist"):
        read_table(tmp_path / "nowhere.csv")


@pytest.mark.parametrize("name", ["found.xlsx", "found", "found.json"])
def test_other_extensions_are_usage_errors_naming_the_three(name: str) -> None:
    with pytest.raises(UsageError, match=r"must end in \.csv, \.jsonl or \.parquet"):
        outputs_for(Path(name))


def test_parquet_without_pyarrow_says_how_to_install_it(monkeypatch: pytest.MonkeyPatch) -> None:
    real = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util, "find_spec", lambda name, *a: None if name == "pyarrow" else real(name, *a)
    )
    with pytest.raises(UsageError) as error:
        outputs_for(Path("found.parquet"))
    assert str(error.value) == PARQUET_HINT
    assert 'pip install "tr-news-scraper[parquet]"' in PARQUET_HINT


def test_an_output_names_its_outside_and_report_files() -> None:
    files = outputs_for(Path("data") / "deprem.CSV")
    assert files.paths == (
        Path("data") / "deprem.CSV",
        Path("data") / "deprem.outside.CSV",
        Path("data") / "deprem.report.json",
    )


def test_existing_files_need_overwrite(tmp_path: Path) -> None:
    files = outputs_for(tmp_path / "found.csv")
    files.report.write_text("{}", encoding="utf-8")
    with pytest.raises(UsageError, match=r"found\.report\.json already exists; add --overwrite"):
        check_writable(files.paths, overwrite=False)
    check_writable(files.paths, overwrite=True)


def test_a_missing_folder_or_a_folder_in_the_way_is_reported(tmp_path: Path) -> None:
    with pytest.raises(UsageError, match=r"the folder .* doesn't exist"):
        check_writable([tmp_path / "missing" / "found.csv"], overwrite=False)
    (tmp_path / "found.csv").mkdir()
    with pytest.raises(UsageError, match="is a folder"):
        check_writable([tmp_path / "found.csv"], overwrite=True)


@pytest.mark.parametrize("stop", [OSError(28, "No space left on device"), KeyboardInterrupt()])
def test_a_failed_save_leaves_no_file_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stop: BaseException
) -> None:
    def fail(frame: pd.DataFrame, path: Path) -> None:
        path.write_text("half", encoding="utf-8")
        raise stop

    monkeypatch.setattr(_files, "write_jsonl", fail)
    files = outputs_for(tmp_path / "found.jsonl")
    content: dict[Path, Any] = {files.report: {"tool": "trnews"}, files.articles: fetched_table()}
    with pytest.raises(WriteError if isinstance(stop, OSError) else KeyboardInterrupt) as error:
        save(content)
    assert list(tmp_path.iterdir()) == []
    if isinstance(stop, OSError):
        assert str(error.value) == f"couldn't write {files.articles}: No space left on device"


def test_save_removes_an_earlier_file_this_run_replaces_with_nothing(tmp_path: Path) -> None:
    files = outputs_for(tmp_path / "found.csv")
    files.articles.write_text("old", encoding="utf-8")
    files.outside.write_text("old", encoding="utf-8")
    save({files.articles: fetched_table()}, remove=[files.outside])
    assert files.articles.read_text(encoding="utf-8-sig") != "old"
    assert [path.name for path in tmp_path.iterdir()] == [files.articles.name]


def earlier_run(tmp_path: Path) -> _files.Outputs:
    """An earlier run's three files, each holding its own name."""
    files = outputs_for(tmp_path / "found.csv")
    for path in files.paths:
        path.write_text(f"earlier {path.name}", encoding="utf-8")
    return files


def assert_earlier_run_kept(tmp_path: Path, files: _files.Outputs) -> None:
    for path in files.paths:
        assert path.read_text(encoding="utf-8") == f"earlier {path.name}"
    assert sorted(path.name for path in tmp_path.iterdir()) == sorted(p.name for p in files.paths)


def refuse(monkeypatch: pytest.MonkeyPatch, busy: Path, stop: BaseException) -> None:
    """Make renaming ``busy`` fail, as Windows does while another program has the file open."""
    rename = Path.replace

    def replace(self: Path, target: Any) -> Path:
        if busy in (self, Path(target)):
            raise stop
        return rename(self, target)

    monkeypatch.setattr(Path, "replace", replace)


@pytest.mark.parametrize("busy", ["articles", "outside", "report"])
def test_a_file_that_cant_be_replaced_leaves_the_earlier_run_as_it_was(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, busy: str
) -> None:
    # A CSV open in Excel can't be replaced on Windows. Swapping in the files before it would
    # leave this run's table next to the earlier run's report, whose range fetch reads.
    files = earlier_run(tmp_path)
    locked = getattr(files, busy)
    refuse(monkeypatch, locked, PermissionError(13, "Permission denied"))
    content: dict[Path, Any] = {
        files.articles: fetched_table(),
        files.outside: fetched_table(),
        files.report: {"tool": "trnews"},
    }
    with pytest.raises(WriteError, match=re.escape(f"{locked}: Permission denied")):
        save(content)
    assert_earlier_run_kept(tmp_path, files)


def test_an_earlier_file_that_cant_be_removed_leaves_the_earlier_run_as_it_was(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = earlier_run(tmp_path)
    refuse(monkeypatch, files.outside, PermissionError(13, "Permission denied"))
    content: dict[Path, Any] = {files.articles: fetched_table(), files.report: {"tool": "trnews"}}
    with pytest.raises(WriteError, match=re.escape(f"the old {files.outside}: Permission denied")):
        save(content, remove=[files.outside])
    assert_earlier_run_kept(tmp_path, files)


@pytest.mark.parametrize("stop", [OSError(5, "Input/output error"), KeyboardInterrupt()])
@pytest.mark.parametrize("earlier", [True, False])
def test_a_save_stopped_while_moving_files_in_puts_back_what_was_there(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stop: BaseException, earlier: bool
) -> None:
    files = earlier_run(tmp_path) if earlier else outputs_for(tmp_path / "found.csv")
    rename = Path.replace

    def replace(self: Path, target: Any) -> Path:
        if self.name.endswith(".part") and Path(target) == files.report:
            raise stop
        return rename(self, target)

    monkeypatch.setattr(Path, "replace", replace)
    content: dict[Path, Any] = {
        files.articles: fetched_table(),
        files.outside: fetched_table(),
        files.report: {"tool": "trnews"},
    }
    with pytest.raises(WriteError if isinstance(stop, OSError) else KeyboardInterrupt):
        save(content)
    if earlier:
        assert_earlier_run_kept(tmp_path, files)
    else:
        assert list(tmp_path.iterdir()) == []


def test_the_report_records_what_was_asked_and_found() -> None:
    report = make_report(
        command="search",
        options={"fetch": True, "obey_robots": True},
        files={"articles": (Path("out") / "found.csv", 2), "outside": None},
        contact=None,
        found=search_result("2 months not read"),
        fetched=fetch_result(),
    )
    assert report["tool"] == "trnews"
    assert report["command"] == "search"
    assert report["keywords"] == ["deprem", "tsunami"]
    assert (report["from"], report["to"]) == ("2023-02-01", "2023-02-28")
    assert report["outlets"] == ["aksam", "sozcu", "star"]
    assert report["searched_at"] == "2026-11-08T14:00:00+03:00"
    assert report["fetched_at"] == "2026-11-08T15:00:00+03:00"
    assert report["files"] == {"articles": {"file": "found.csv", "rows": 2}, "outside": None}
    assert report["search"]["report"][0] == {
        "outlet": "aksam",
        "name": "Akşam",
        "status": "ok",
        "articles": 1,
        "detail": "2 months not read",
    }
    assert report["search"]["gaps"][0]["reason"] == "before-archive"
    assert report["fetch"]["version"] == "1.0.0"
    assert [row["failed"] for row in report["fetch"]["report"]] == [0, 1, 0]
    assert json.loads(json.dumps(report)) == report


def test_the_report_never_holds_the_contact_address() -> None:
    contact = "mailto:someone@example.org"
    report = make_report(
        command="search",
        options={"fetch": False},
        files={"articles": (Path("found.csv"), 2)},
        contact=contact,
        found=search_result(f"refused tr-news-scraper/1.0 ({contact})"),
    )
    assert contact not in json.dumps(report)
    assert report["search"]["report"][0]["detail"] == "refused tr-news-scraper/1.0 ([contact])"


def test_a_two_step_fetch_carries_the_search_over(tmp_path: Path) -> None:
    earlier = make_report(
        command="search",
        options={"fetch": False},
        files={"articles": (tmp_path / "found.csv", 2)},
        contact=None,
        found=search_result("ok"),
    )
    save({tmp_path / "found.report.json": earlier})
    loaded = read_report(tmp_path / "found.report.json")
    assert loaded == earlier
    report = make_report(
        command="fetch",
        options={},
        files={"articles": (tmp_path / "fetched.csv", 2)},
        contact=None,
        fetched=fetch_result(),
        earlier=loaded,
        source=tmp_path / "found.csv",
    )
    assert report["input"] == "found.csv"
    assert report["search"] == earlier["search"]
    assert report["searched_at"] == earlier["searched_at"]
    assert report["outlets"] == ["aksam", "sozcu", "star"]


def test_a_missing_or_damaged_report_file(tmp_path: Path) -> None:
    assert read_report(tmp_path / "none.report.json") is None
    (tmp_path / "bad.report.json").write_text("[1]", encoding="utf-8")
    with pytest.raises(UsageError, match="isn't a trnews report file"):
        read_report(tmp_path / "bad.report.json")
    (tmp_path / "broken.report.json").write_text("{", encoding="utf-8")
    with pytest.raises(UsageError, match="can't be read"):
        read_report(tmp_path / "broken.report.json")
