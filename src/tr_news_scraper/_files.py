"""trnews's files: tables as CSV, JSONL or Parquet, and the report file beside them (internal).

Data files are always UTF-8. A CSV file starts with a byte-order mark, so Excel shows Turkish
letters, and a text cell that a spreadsheet would run as a formula starts with an apostrophe;
``read_table`` removes it again. Times are ISO 8601 with their offset and days ``YYYY-MM-DD``,
and reading a file restores the column types of ``search()`` and ``fetch()``.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from tr_news_scraper._table import ARTICLE_COLUMNS, DAY_DTYPE
from tr_news_scraper._version import __version__

if TYPE_CHECKING:
    import pandas as pd

    from tr_news_scraper._fetched import FetchResult
    from tr_news_scraper._table import SearchResult

FORMATS = (".csv", ".jsonl", ".parquet")
SEPARATORS = (",", ";")
PARQUET_HINT = 'Parquet files need pyarrow: pip install "tr-news-scraper[parquet]"'

STRING_COLUMNS = frozenset(
    {
        "outlet",
        "month",
        "title",
        "url",
        "matched",
        "reasons",
        "source",
        "author",
        "text",
        "text_matched",
        "error",
    }
)
NEVER_MISSING = frozenset({"matched", "reasons", "text_matched"})
"""Columns that hold a string on every row, "" when empty; a CSV file can't tell "" from none."""
DAY_COLUMNS = frozenset({"day"})
TIME_COLUMNS = frozenset({"lastmod", "published", "fetched_at"})
COUNT_COLUMNS = frozenset({"copy_group"})

_FORMULA = re.compile(r"^(?='*[=+\-@\t\r])")
"""Where an apostrophe goes before a cell a spreadsheet would read as a formula. Cells that
already start with apostrophes before such a character get one more, so reading is exact."""
_ESCAPED = re.compile(r"^'(?='*[=+\-@\t\r])")
_ISTANBUL = "Europe/Istanbul"


class UsageError(Exception):
    """A mistake in the command line or in its files, found before any request."""


class WriteError(Exception):
    """A file couldn't be written."""


@dataclass(frozen=True, slots=True)
class Outputs:
    """The files a command writes for ``-o NAME.EXT`` (C3–C5)."""

    articles: Path
    outside: Path
    report: Path

    @property
    def paths(self) -> tuple[Path, Path, Path]:
        return (self.articles, self.outside, self.report)


def table_format(path: Path) -> str:
    """The format ``path``'s extension chooses: ``.csv``, ``.jsonl`` or ``.parquet`` (C2)."""
    suffix = path.suffix.lower()
    if suffix not in FORMATS:
        raise UsageError(f"{path}: the file name must end in .csv, .jsonl or .parquet")
    if suffix == ".parquet" and importlib.util.find_spec("pyarrow") is None:
        raise UsageError(PARQUET_HINT)
    return suffix


def outputs_for(path: Path) -> Outputs:
    """``NAME.EXT``, ``NAME.outside.EXT`` and ``NAME.report.json`` for ``-o NAME.EXT``."""
    table_format(path)
    return Outputs(
        articles=path,
        outside=path.with_name(f"{path.stem}.outside{path.suffix}"),
        report=report_path(path),
    )


def report_path(path: Path) -> Path:
    """The report file that belongs to the table at ``path``."""
    return path.with_name(f"{path.stem}.report.json")


def check_writable(paths: Sequence[Path], *, overwrite: bool) -> None:
    """Stop before any request if a file exists without ``overwrite``, or can't be written (C3)."""
    for path in paths:
        if not path.parent.is_dir():
            raise UsageError(f"the folder {path.parent} doesn't exist")
        if path.is_dir():
            raise UsageError(f"{path} is a folder")
        if path.exists() and not overwrite:
            raise UsageError(f"{path} already exists; add --overwrite to replace it")


def save(
    files: Mapping[Path, pd.DataFrame | Mapping[str, Any]],
    *,
    separator: str = ",",
    remove: Sequence[Path] = (),
) -> None:
    """Write every table and report file, then move them into place together, so a failure or
    Ctrl+C leaves no half-written file (C9). Files in ``remove`` that exist are deleted after:
    an earlier run's files that this run replaces with nothing."""
    staged: dict[Path, Path] = {}
    try:
        for path, content in files.items():
            temporary = path.with_name(f".{path.name}.{os.getpid()}.part")
            staged[path] = temporary
            _write(temporary, content, path=path, separator=separator)
        for path, temporary in staged.items():
            _move(temporary, path)
        for path in remove:
            if path not in files:
                _remove(path)
    finally:
        for temporary in staged.values():
            temporary.unlink(missing_ok=True)


def _write(
    temporary: Path, content: pd.DataFrame | Mapping[str, Any], *, path: Path, separator: str
) -> None:
    try:
        if isinstance(content, Mapping):
            text = json.dumps(content, ensure_ascii=False, indent=2, allow_nan=False)
            temporary.write_text(text + "\n", encoding="utf-8", newline="\n")
            return
        kind = table_format(path)
        if kind == ".csv":
            write_csv(content, temporary, separator=separator)
        elif kind == ".jsonl":
            write_jsonl(content, temporary)
        else:
            content.to_parquet(temporary, index=False, engine="pyarrow")
    except OSError as error:
        raise WriteError(f"couldn't write {path}: {error.strerror or error}") from error


def _move(temporary: Path, path: Path) -> None:
    try:
        temporary.replace(path)
    except OSError as error:
        raise WriteError(f"couldn't write {path}: {error.strerror or error}") from error


def _remove(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError as error:
        raise WriteError(f"couldn't remove the old {path}: {error.strerror or error}") from error


def write_csv(frame: pd.DataFrame, path: Path, *, separator: str = ",") -> None:
    """UTF-8 with a byte-order mark and CRLF line ends; text keeps its line breaks, quoted."""
    names = [str(name) for name in frame.columns]
    columns = [[_unformula(cell) for cell in cells(frame[name])] for name in frame.columns]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file, delimiter=separator, lineterminator="\r\n")
        writer.writerow(names)
        writer.writerows(zip(*columns, strict=True))


def write_jsonl(frame: pd.DataFrame, path: Path) -> None:
    """One UTF-8 JSON object per line, ``null`` for a missing value."""
    names = [str(name) for name in frame.columns]
    columns = [cells(frame[name]) for name in frame.columns]
    with path.open("w", encoding="utf-8", newline="\n") as file:
        for row in zip(*columns, strict=True):
            line = json.dumps(
                dict(zip(names, row, strict=True)), ensure_ascii=False, allow_nan=False
            )
            file.write(line + "\n")


def cells(series: pd.Series) -> list[Any]:
    """A column as plain values: ``str``, ``int``, ``float``, ``bool`` or ``None``. Times are
    ISO 8601 with their offset, and a column of midnights is written as days."""
    import numpy as np
    import pandas as pd

    missing = series.isna().tolist()
    if isinstance(series.dtype, pd.DatetimeTZDtype):
        return [
            None if gone else value.isoformat() for value, gone in zip(series, missing, strict=True)
        ]
    if pd.api.types.is_datetime64_dtype(series.dtype):
        values = [value for value, gone in zip(series, missing, strict=True) if not gone]
        if all(value == value.normalize() for value in values):
            return [
                None if gone else value.date().isoformat()
                for value, gone in zip(series, missing, strict=True)
            ]
        return [
            None if gone else value.isoformat() for value, gone in zip(series, missing, strict=True)
        ]
    values = series.astype(object).tolist()
    return [
        None if gone else value.item() if isinstance(value, np.generic) else value
        for value, gone in zip(values, missing, strict=True)
    ]


def _unformula(cell: Any) -> Any:
    return _FORMULA.sub("'", cell, count=1) if isinstance(cell, str) else cell


def read_table(path: Path) -> pd.DataFrame:
    """A table written by trnews, or any table with the same columns, with search's and fetch's
    column types restored (C6)."""
    kind = table_format(path)
    if not path.is_file():
        raise UsageError(f"{path} doesn't exist")
    if kind == ".csv":
        frame = _read_csv(path)
    elif kind == ".jsonl":
        frame = _read_jsonl(path)
    else:
        frame = _read_parquet(path)
    return restore_types(frame, path)


def _read_csv(path: Path) -> pd.DataFrame:
    import pandas as pd

    try:
        with path.open(encoding="utf-8-sig", newline="") as file:
            header = file.readline()
        separator = ";" if ";" in header and "," not in header else ","
        frame = pd.read_csv(
            path,
            sep=separator,
            dtype=str,
            keep_default_na=False,
            na_values=[""],
            encoding="utf-8-sig",
        )
    except UnicodeDecodeError as error:
        raise UsageError(
            f"{path} isn't UTF-8 text; if Excel saved it, save it as 'CSV UTF-8' instead"
        ) from error
    except (pd.errors.ParserError, pd.errors.EmptyDataError) as error:
        raise UsageError(f"{path} can't be read as CSV: {error}") from error
    for name in frame.columns:
        frame[name] = frame[name].str.replace(_ESCAPED, "", n=1, regex=True)
    return frame


def _read_jsonl(path: Path) -> pd.DataFrame:
    import pandas as pd

    records: list[dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8-sig") as file:
            for number, line in enumerate(file, start=1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as error:
                    raise UsageError(f"{path}: line {number} isn't JSON ({error.msg})") from error
                if not isinstance(record, dict):
                    raise UsageError(f"{path}: line {number} isn't a JSON object")
                records.append(record)
    except UnicodeDecodeError as error:
        raise UsageError(f"{path} isn't UTF-8 text") from error
    if not records:
        return pd.DataFrame({name: pd.Series([], dtype=object) for name in ARTICLE_COLUMNS})
    return pd.DataFrame(records, dtype=object)


def _read_parquet(path: Path) -> pd.DataFrame:
    import pandas as pd

    try:
        return pd.read_parquet(path, engine="pyarrow")
    except (ValueError, OSError) as error:  # pyarrow's ArrowInvalid is a ValueError
        raise UsageError(f"{path} can't be read as Parquet: {error}") from error


def restore_types(frame: pd.DataFrame, path: Path) -> pd.DataFrame:
    """The known columns with search's and fetch's types; other columns as they were read."""
    table = frame.copy()
    for name in table.columns:
        if name in DAY_COLUMNS:
            table[name] = _days(table[name], path, name)
        elif name in TIME_COLUMNS:
            table[name] = _times(table[name], path, name)
        elif name in COUNT_COLUMNS:
            table[name] = _counts(table[name], path, name)
        elif name in STRING_COLUMNS:
            text = table[name].astype("string")
            table[name] = text.fillna("") if name in NEVER_MISSING else text
    return table


def _days(series: pd.Series, path: Path, name: str) -> pd.Series:
    import pandas as pd

    if isinstance(series.dtype, pd.DatetimeTZDtype):
        days = series.dt.tz_convert(_ISTANBUL).dt.tz_localize(None)
    elif pd.api.types.is_datetime64_dtype(series.dtype):
        days = series
    else:
        text = series.astype("string")
        days = pd.to_datetime(text, format="%Y-%m-%d", errors="coerce")
        _check(text, days, path, name, "a day such as 2023-02-12")
    typed: pd.Series = days.dt.normalize().astype(DAY_DTYPE)
    return typed


def _times(series: pd.Series, path: Path, name: str) -> pd.Series:
    import pandas as pd

    if isinstance(series.dtype, pd.DatetimeTZDtype):
        times = series
    elif pd.api.types.is_datetime64_dtype(series.dtype):
        times = series.dt.tz_localize(_ISTANBUL)
    else:
        text = series.astype("string")
        times = pd.to_datetime(text, format="ISO8601", utc=True, errors="coerce")
        _check(text, times, path, name, "a time such as 2023-02-12T06:02:00+03:00")
    typed: pd.Series = times.dt.tz_convert(_ISTANBUL).astype(pd.DatetimeTZDtype("ns", _ISTANBUL))
    return typed


def _counts(series: pd.Series, path: Path, name: str) -> pd.Series:
    import pandas as pd

    numbers = pd.to_numeric(series, errors="coerce")
    whole = numbers.where(numbers.isna() | (numbers % 1 == 0))
    _check(series, whole, path, name, "a whole number")
    return whole.astype("Int64")


def _check(given: pd.Series, parsed: pd.Series, path: Path, name: str, expected: str) -> None:
    bad = (parsed.isna() & given.notna()).tolist()
    if any(bad):
        row = bad.index(True)
        raise UsageError(f"{path}: row {row + 1}'s {name} is {given.iloc[row]!r}, not {expected}")


def table_rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """A table as JSON objects, one per row."""
    names = [str(name) for name in frame.columns]
    columns = [cells(frame[name]) for name in frame.columns]
    return [dict(zip(names, row, strict=True)) for row in zip(*columns, strict=True)]


def read_report(path: Path) -> dict[str, Any] | None:
    """The report file at ``path``, or ``None`` if there is none."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise UsageError(f"{path} can't be read: {error}") from error
    if not isinstance(data, dict):
        raise UsageError(f"{path} isn't a trnews report file")
    return data


def make_report(
    *,
    command: str,
    options: Mapping[str, Any],
    files: Mapping[str, tuple[Path, int] | None],
    contact: str | None,
    found: SearchResult | None = None,
    fetched: FetchResult | None = None,
    earlier: Mapping[str, Any] | None = None,
    source: Path | None = None,
) -> dict[str, Any]:
    """What was asked, when, by which version, and each outlet's report and gaps (C4).

    ``earlier`` is the report file of the table a ``trnews fetch`` read, whose search it carries
    over. The contact address is never recorded: options never include it, and any trace of it
    in the outlets' messages is replaced.
    """
    keywords: Sequence[str] = ()
    first: date | None = None
    after: date | None = None
    outlets: list[str] = []
    searched_at: Any = None
    search: Any = None
    if found is not None:
        keywords, first, after = found.keywords, found.start, found.end
        outlets = [outlet.id for outlet in found.outlets]
        searched_at = found.searched_at.isoformat()
        search = {
            "version": found.version,
            "report": table_rows(found.report),
            "gaps": table_rows(found.gaps),
        }
    elif earlier is not None:
        listed = earlier.get("outlets")
        outlets = [str(item) for item in listed] if isinstance(listed, list) else []
        searched_at = earlier.get("searched_at")
        search = earlier.get("search")
    if fetched is not None:
        keywords, first, after = fetched.keywords, fetched.start, fetched.end
        if not outlets:
            outlets = [str(outlet) for outlet in fetched.report["outlet"]]
    report = {
        "tool": "trnews",
        "version": __version__,
        "command": command,
        "options": dict(options),
        "input": None if source is None else source.name,
        "keywords": list(keywords),
        "from": None if first is None else first.isoformat(),
        "to": None if after is None else (after - timedelta(days=1)).isoformat(),
        "outlets": outlets,
        "searched_at": searched_at,
        "fetched_at": None if fetched is None else fetched.fetched_at.isoformat(),
        "files": {
            role: None if entry is None else {"file": entry[0].name, "rows": entry[1]}
            for role, entry in files.items()
        },
        "search": search,
        "fetch": None
        if fetched is None
        else {"version": fetched.version, "report": table_rows(fetched.report)},
    }
    scrubbed: dict[str, Any] = _without(report, contact)
    return scrubbed


def _without(value: Any, contact: str | None) -> Any:
    """``value`` with every occurrence of ``contact`` in its strings replaced."""
    if not contact:
        return value
    if isinstance(value, str):
        return value.replace(contact, "[contact]")
    if isinstance(value, dict):
        return {key: _without(item, contact) for key, item in value.items()}
    if isinstance(value, list):
        return [_without(item, contact) for item in value]
    return value
