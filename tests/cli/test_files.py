"""trnews's files: formats, types, paths, the overwrite check and the report file (C2–C6)."""

from __future__ import annotations

import importlib.util
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from tr_news_scraper import _files
from tr_news_scraper._fetched import FetchResult
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
from tr_news_scraper._table import (
    DAY_DTYPE,
    TIME_DTYPE,
    SearchResult,
    day_series,
    string_series,
    time_series,
)
from tr_news_scraper.outlets import get
from tr_news_scraper.outlets._dates import ISTANBUL

HAS_PYARROW = importlib.util.find_spec("pyarrow") is not None
FORMATS = [
    ".csv",
    ".jsonl",
    pytest.param(
        ".parquet", marks=pytest.mark.skipif(not HAS_PYARROW, reason="needs the parquet extra")
    ),
]
BOM = b"\xef\xbb\xbf"
LINES = 'Birinci satır, virgüllü.\nİkinci satır; noktalı virgüllü ve "tırnaklı".'


def fetched_table() -> pd.DataFrame:
    """Search's columns plus fetch's, with every type, empty values and awkward text."""
    return pd.DataFrame(
        {
            "outlet": string_series(["aksam", "sozcu", "star"]),
            "month": string_series(["2023-02", "2023-02", "2023-02"]),
            "day": day_series([date(2023, 2, 6), None, date(2023, 2, 7)]),
            "title": string_series(["Akşam'da deprem", None, '=HYPERLINK("http://x", "x")']),
            "url": string_series(
                [
                    "https://www.aksam.com.tr/guncel/deprem/haber-1",
                    "https://www.sozcu.com.tr/deprem-2",
                    "https://www.star.com.tr/guncel/deprem-3",
                ]
            ),
            "matched": string_series(["deprem", "deprem, tsunami", "deprem"]),
            "reasons": string_series(["title", "url", "title"]),
            "lastmod": time_series([datetime(2023, 2, 6, 4, 17, tzinfo=ISTANBUL), None, None]),
            "source": string_series(["sitemap", "sitemap", "sitemap"]),
            "published": time_series([datetime(2023, 2, 6, 4, 2, tzinfo=ISTANBUL), None, None]),
            "author": string_series(["Ayşe Demir", None, "'=x"]),
            "text": string_series([LINES, None, "-15 derece"]),
            "text_matched": string_series(["deprem", "", ""]),
            "copy_group": pd.Series([1, None, 1], dtype="Int64"),
            "fetched_at": time_series(
                [datetime(2026, 11, 8, 14, 3, 12, 345678, tzinfo=ISTANBUL), None, None]
            ),
            "error": string_series([None, "HTTP 404", None]),
        }
    )


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
    files.outside.write_text("old", encoding="utf-8")
    save({files.articles: fetched_table()}, remove=[files.outside])
    assert files.articles.exists()
    assert not files.outside.exists()


def search_result(detail: str) -> SearchResult:
    return SearchResult(
        articles=fetched_table().iloc[:, :9],
        report=pd.DataFrame({"outlet": string_series(["star"]), "detail": string_series([detail])}),
        gaps=pd.DataFrame({"outlet": string_series([]), "reason": string_series([])}),
        keywords=("deprem", "tsunami"),
        start=date(2023, 2, 1),
        end=date(2023, 3, 1),
        outlets=(get("star"), get("aksam")),
        searched_at=datetime(2026, 11, 8, 14, 0, tzinfo=ISTANBUL),
        version="1.0.0",
    )


def fetch_result() -> FetchResult:
    table = fetched_table()
    return FetchResult(
        articles=table.iloc[:2],
        outside=table.iloc[2:],
        report=pd.DataFrame({"outlet": string_series(["star"]), "failed": [1]}),
        keywords=("deprem", "tsunami"),
        start=date(2023, 2, 1),
        end=date(2023, 3, 1),
        outlets=(get("star"), get("aksam")),
        fetched_at=datetime(2026, 11, 8, 15, 0, tzinfo=ISTANBUL),
        version="1.0.0",
    )


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
    assert report["outlets"] == ["star", "aksam"]
    assert report["searched_at"] == "2026-11-08T14:00:00+03:00"
    assert report["fetched_at"] == "2026-11-08T15:00:00+03:00"
    assert report["files"] == {"articles": {"file": "found.csv", "rows": 2}, "outside": None}
    assert report["search"]["report"] == [{"outlet": "star", "detail": "2 months not read"}]
    assert report["fetch"] == {"version": "1.0.0", "report": [{"outlet": "star", "failed": 1}]}
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
    assert report["outlets"] == ["star", "aksam"]


def test_a_missing_or_damaged_report_file(tmp_path: Path) -> None:
    assert read_report(tmp_path / "none.report.json") is None
    (tmp_path / "bad.report.json").write_text("[1]", encoding="utf-8")
    with pytest.raises(UsageError, match="isn't a trnews report file"):
        read_report(tmp_path / "bad.report.json")
    (tmp_path / "broken.report.json").write_text("{", encoding="utf-8")
    with pytest.raises(UsageError, match="can't be read"):
        read_report(tmp_path / "broken.report.json")
