"""trnews: search Turkish news archives and read the articles from the command line (internal).

A thin layer over ``search()``, ``fetch()`` and ``coverage()``. Every argument and output file is
checked before the first request. Data goes to files; progress, the summary and errors go to
standard error, and standard output carries only ``trnews coverage``'s table.
"""

from __future__ import annotations

import argparse
import logging
import sys
import threading
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, TextIO

from tr_news_scraper import coverage, fetch, search
from tr_news_scraper._files import (
    SEPARATORS,
    Outputs,
    UsageError,
    WriteError,
    cells,
    check_writable,
    make_report,
    outputs_for,
    read_report,
    read_table,
    report_path,
    save,
    table_format,
)
from tr_news_scraper._http import HttpConfig
from tr_news_scraper._search import parse_day, parse_keywords
from tr_news_scraper._version import __version__
from tr_news_scraper.errors import FetchFailed, SearchFailed
from tr_news_scraper.matching import KeywordQuery
from tr_news_scraper.outlets import builtin, get

if TYPE_CHECKING:
    import pandas as pd

    from tr_news_scraper import FetchResult, SearchResult

OK, FAILED, USAGE, STOPPED = 0, 1, 2, 130
ROBOTS_WARNING = (
    "warning: --ignore-robots-txt: robots.txt won't be checked. Use it only with each site's "
    "permission; you are responsible for these requests."
)
COVERAGE_SHOWN = ("outlet", "name", "method", "earliest", "headlines")
HEALTH_SHOWN = ("ok", "oldest", "newest", "sample")
SHOWN_INFO = frozenset({"tr_news_scraper.search", "tr_news_scraper.fetch"})
"""The loggers whose INFO lines show without -v: one line per outlet, and fetch's progress."""

Command = Callable[[argparse.Namespace, "Console"], int]


class Console:
    """What trnews says on standard error: progress and the summary unless quiet; warnings and
    errors always (C7)."""

    def __init__(self, stream: TextIO, *, quiet: bool = False) -> None:
        self.stream = stream
        self.quiet = quiet

    def say(self, text: str) -> None:
        if not self.quiet:
            self.write(text)

    def write(self, text: str) -> None:
        self.stream.write(text + "\n")
        self.stream.flush()


class _LogHandler(logging.Handler):
    """The library's log lines, on the console."""

    def __init__(self, console: Console, *, verbose: bool) -> None:
        super().__init__(logging.INFO)
        self.console = console
        self.verbose = verbose

    def filter(self, record: logging.LogRecord) -> bool:
        if self.console.quiet:
            return record.levelno >= logging.ERROR
        return record.levelno >= logging.WARNING or self.verbose or record.name in SHOWN_INFO

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = record.getMessage()
        except (TypeError, ValueError):
            self.handleError(record)
            return
        prefix = "  " if record.levelno < logging.WARNING else "  warning: "
        self.console.write(prefix + message)


@contextmanager
def _showing_logs(console: Console, *, verbose: bool) -> Iterator[None]:
    """Show the library's log on ``console`` while a command runs."""
    logger = logging.getLogger("tr_news_scraper")
    handler = _LogHandler(console, verbose=verbose)
    level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        yield
    finally:
        logger.removeHandler(handler)
        logger.setLevel(level)


def build_parser() -> argparse.ArgumentParser:
    """trnews's commands and options (C1)."""
    parser = argparse.ArgumentParser(
        prog="trnews",
        description="Search Turkish news archives by keyword and date range; read the articles.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s (tr-news-scraper) {__version__}"
    )
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")
    find = commands.add_parser(
        "search",
        parents=[_network_options(), _cache_options(), _file_options()],
        help="find articles whose headline or URL names a keyword",
        description=(
            "Find news articles whose headline or URL names any of the keywords, published from "
            "--from to --to (both included, in Türkiye). Writes the articles to FILE and what was "
            "searched to NAME.report.json beside it; with --fetch, also each article's text."
        ),
    )
    find.add_argument(
        "keywords",
        nargs="+",
        metavar="KEYWORD",
        help='a word or phrase; any of them may match. "word*" matches as a prefix',
    )
    find.add_argument("--from", dest="first", required=True, metavar="DATE", help="first day")
    find.add_argument("--to", dest="last", required=True, metavar="DATE", help="last day, included")
    find.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        metavar="FILE",
        help="where the articles go: NAME.csv, NAME.jsonl or NAME.parquet",
    )
    find.add_argument(
        "--outlets", metavar="ID,...", help="built-in outlet ids, comma-separated; all by default"
    )
    find.add_argument(
        "--fetch",
        action="store_true",
        help="also download every article and read its text, author and time",
    )
    find.set_defaults(run=_search_command)
    take = commands.add_parser(
        "fetch",
        parents=[_network_options(), _cache_options(), _file_options()],
        help="read the articles in a table, such as one trnews search wrote",
        description=(
            "Download every article in FILE, any table with outlet and url columns, and read its "
            "text, author and publication time. Without --from and --to, the keywords and range "
            "come from FILE's report file, as with search --fetch."
        ),
    )
    take.add_argument(
        "file", type=Path, metavar="FILE", help="the articles: a .csv, .jsonl or .parquet table"
    )
    take.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        metavar="FILE",
        help="where the articles go: NAME.csv, NAME.jsonl or NAME.parquet",
    )
    take.add_argument(
        "--from",
        dest="first",
        metavar="DATE",
        help="first day; rows whose page dates them outside the range go to NAME.outside",
    )
    take.add_argument("--to", dest="last", metavar="DATE", help="last day, included")
    take.set_defaults(run=_fetch_command)
    show = commands.add_parser(
        "coverage",
        parents=[_network_options(), _file_options()],
        help="what each outlet's archive covers, and whether it works today",
        description=(
            "Show how each outlet is read and from when, without a request. --check also "
            "reads each archive now: about 2 requests per outlet."
        ),
    )
    show.add_argument(
        "--check", action="store_true", help="also check every archive now and add its health"
    )
    show.add_argument(
        "-o",
        "--output",
        type=Path,
        metavar="FILE",
        help="write the table to FILE (.csv, .jsonl or .parquet) instead of printing it",
    )
    show.set_defaults(run=_coverage_command)
    return parser


def _network_options() -> argparse.ArgumentParser:
    options = argparse.ArgumentParser(add_help=False)
    group = options.add_argument_group("requests")
    group.add_argument(
        "--contact",
        metavar="TEXT",
        help="added to the User-Agent, such as mailto:you@example.org; never written to files",
    )
    group.add_argument(
        "--ignore-robots-txt",
        action="store_true",
        help="don't check robots.txt (warns; only with each site's permission)",
    )
    group.add_argument(
        "--cache-dir", type=Path, metavar="DIR", help="where responses and records are cached"
    )
    return options


def _cache_options() -> argparse.ArgumentParser:
    options = argparse.ArgumentParser(add_help=False)
    group = options.add_argument_group("cache")
    group.add_argument(
        "--offline", action="store_true", help="answer only from the cache, without a request"
    )
    group.add_argument(
        "--refresh",
        action="store_true",
        help="download articles again even if they're in the cache",
    )
    return options


def _file_options() -> argparse.ArgumentParser:
    options = argparse.ArgumentParser(add_help=False)
    group = options.add_argument_group("output")
    group.add_argument(
        "--separator",
        choices=SEPARATORS,
        metavar="SEP",
        help='the CSV separator: "," (the default) or ";", which suits Excel with Turkish '
        "regional settings",
    )
    group.add_argument("--overwrite", action="store_true", help="replace files that exist")
    loudness = group.add_mutually_exclusive_group()
    loudness.add_argument(
        "-q", "--quiet", action="store_true", help="no progress or summary; errors only"
    )
    loudness.add_argument("-v", "--verbose", action="store_true", help="also the library's log")
    return options


def main(argv: Sequence[str] | None = None) -> int:
    """Run ``trnews`` with ``argv`` (default: the command line) and return its exit code."""
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as stop:  # --help, --version and usage mistakes
        return stop.code if isinstance(stop.code, int) else OK
    console = Console(sys.stderr, quiet=args.quiet)
    run: Command = args.run
    try:
        with _showing_logs(console, verbose=args.verbose):
            return run(args, console)
    except UsageError as error:
        console.write(f"trnews {args.command}: error: {error}")
        return USAGE
    except (SearchFailed, FetchFailed, WriteError) as error:
        console.write(f"trnews {args.command}: {error}")
        return FAILED
    except KeyboardInterrupt:
        console.write("Stopped.")
        return STOPPED


def keywords_from(given: Sequence[str]) -> tuple[str, ...]:
    """The keywords as search() will read them, or a usage error (C1)."""
    try:
        return KeywordQuery(parse_keywords(given)).keywords
    except ValueError as error:
        raise UsageError(str(error)) from error


def day_from(text: str, option: str) -> date:
    """A ``YYYY-MM-DD`` option as a day, or a usage error (C1)."""
    try:
        return parse_day(text, option)
    except ValueError as error:
        raise UsageError(
            f"{option} must be a day as YYYY-MM-DD, such as 2023-02-01, not {text!r}"
        ) from error


def range_from(first: str | None, last: str | None) -> tuple[date, date] | None:
    """``--from`` and ``--to`` as the library's [start, end): ``--to`` is the last day,
    included (D2). ``None`` when neither is given."""
    if first is None and last is None:
        return None
    if first is None or last is None:
        raise UsageError("give both --from and --to, or neither")
    start, final = day_from(first, "--from"), day_from(last, "--to")
    if final < start:
        raise UsageError(f"--to ({final}) is before --from ({start})")
    return start, final + timedelta(days=1)


def outlets_from(text: str | None) -> tuple[str, ...] | None:
    """``--outlets a,b`` as built-in ids; an unknown id lists the valid ones (C1)."""
    if text is None:
        return None
    ids = tuple(dict.fromkeys(part.strip() for part in text.split(",") if part.strip()))
    if not ids:
        raise UsageError("--outlets needs at least one outlet id, such as star")
    for outlet_id in ids:
        try:
            get(outlet_id)
        except ValueError as error:
            raise UsageError(str(error)) from error
    return ids


def check_requests(args: argparse.Namespace, console: Console) -> None:
    """Check ``--contact`` and warn about ``--ignore-robots-txt`` before the first request
    (C11). The warning shows even with -q."""
    try:
        HttpConfig(contact=args.contact)
    except ValueError as error:
        raise UsageError(
            "--contact must be printable ASCII without parentheses or semicolons, "
            "such as mailto:you@example.org"
        ) from error
    if args.ignore_robots_txt:
        console.write(ROBOTS_WARNING)


def check_separator(args: argparse.Namespace, path: Path | None) -> str:
    """The CSV separator; ``--separator`` with another format is a usage error."""
    if args.separator is not None and (path is None or table_format(path) != ".csv"):
        raise UsageError("--separator applies only to .csv files")
    return str(args.separator or ",")


class Tracker:
    """How far fetch has got, outlet by outlet; workers report from their own threads."""

    def __init__(self, total: int) -> None:
        self.total = total
        self._counts: dict[str, int] = {}
        self._lock = threading.Lock()

    def update(self, outlet: str, done: int, total: int) -> None:
        with self._lock:
            self._counts[outlet] = done

    @property
    def done(self) -> int:
        with self._lock:
            return sum(self._counts.values())


def _search_command(args: argparse.Namespace, console: Console) -> int:
    keywords = keywords_from(args.keywords)
    span = range_from(args.first, args.last)
    if span is None:  # argparse requires --from and --to
        raise UsageError("give --from and --to")
    start, end = span
    outlets = outlets_from(args.outlets)
    files = outputs_for(args.output)
    separator = check_separator(args, args.output)
    if args.refresh and not args.fetch:
        raise UsageError("--refresh applies only with --fetch")
    check_writable(files.paths, overwrite=args.overwrite)
    check_requests(args, console)
    searched = len(builtin()) if outlets is None else len(outlets)
    console.say(
        f"Searching {_count(searched, 'outlet')} for {', '.join(keywords)}, {_span(start, end)} ..."
    )
    try:
        found = search(
            keywords,
            start,
            end,
            outlets=outlets,
            contact=args.contact,
            obey_robots=not args.ignore_robots_txt,
            offline=args.offline,
            cache_dir=args.cache_dir,
        )
    except KeyboardInterrupt:
        console.write("Stopped while searching; no file was written.")
        return STOPPED
    console.say(str(found))
    fetched = None
    if args.fetch:
        fetched = _read(found, len(found.articles), args, console)
        if fetched is None:
            return STOPPED
    _save_outputs(
        files,
        found.articles if fetched is None else fetched.articles,
        None if fetched is None else fetched.outside,
        args=args,
        console=console,
        separator=separator,
        command="search",
        options={
            "outlets": None if outlets is None else list(outlets),
            "fetch": bool(args.fetch),
            "obey_robots": not args.ignore_robots_txt,
            "offline": bool(args.offline),
            "refresh": bool(args.refresh),
        },
        found=found,
        fetched=fetched,
    )
    return OK


def _read(
    articles: SearchResult | pd.DataFrame,
    total: int,
    args: argparse.Namespace,
    console: Console,
    **scope: Any,
) -> FetchResult | None:
    """Fetch every article, or ``None`` after saying how to continue if stopped (C9)."""
    tracker = Tracker(total)
    console.say(f"Reading {_count(total, 'article')} ...")
    try:
        fetched = fetch(
            articles,
            progress=tracker.update,
            contact=args.contact,
            obey_robots=not args.ignore_robots_txt,
            offline=args.offline,
            refresh=args.refresh,
            cache_dir=args.cache_dir,
            **scope,
        )
    except KeyboardInterrupt:
        console.write(
            f"Stopped after {tracker.done:,} of {_count(total, 'article')}; no file was written."
        )
        console.write(
            "The articles read are saved in the cache: run the same command again to continue."
        )
        return None
    console.say(str(fetched))
    return fetched


def _save_outputs(
    files: Outputs,
    articles: pd.DataFrame,
    outside: pd.DataFrame | None,
    *,
    args: argparse.Namespace,
    console: Console,
    separator: str,
    **report: Any,
) -> None:
    """Write the articles, the outside rows if there are any, and the report file (C3–C5)."""
    content: dict[Path, pd.DataFrame | dict[str, Any]] = {files.articles: articles}
    entries: dict[str, tuple[Path, int] | None] = {
        "articles": (files.articles, len(articles)),
        "outside": None,
    }
    if outside is not None and len(outside):
        content[files.outside] = outside
        entries["outside"] = (files.outside, len(outside))
    content[files.report] = make_report(files=entries, contact=args.contact, **report)
    save(content, separator=separator, remove=[files.outside])
    written = [f"{path} ({_count(rows, 'row')})" for path, rows in filter(None, entries.values())]
    console.say(f"Wrote {_join([*written, str(files.report)])}.")


def _count(number: int, word: str) -> str:
    return f"{number:,} {word if number == 1 else word + 's'}"


def _span(start: date, end: date) -> str:
    last = end - timedelta(days=1)
    return str(start) if last == start else f"{start} to {last}"


def _join(items: Sequence[str]) -> str:
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"


def _fetch_command(args: argparse.Namespace, console: Console) -> int:
    source: Path = args.file
    files = outputs_for(args.output)
    separator = check_separator(args, args.output)
    given = range_from(args.first, args.last)
    table = read_table(source)
    check_table(table, source)
    earlier = read_report(report_path(source))
    keywords, recorded = scope_from(earlier, report_path(source))
    start, end = given or recorded or (None, None)
    check_writable(files.paths, overwrite=args.overwrite)
    check_requests(args, console)
    fetched = _read(
        table,
        len(table),
        args,
        console,
        keywords=keywords or None,
        start=start,
        end=end,
    )
    if fetched is None:
        return STOPPED
    _save_outputs(
        files,
        fetched.articles,
        fetched.outside,
        args=args,
        console=console,
        separator=separator,
        command="fetch",
        options={
            "obey_robots": not args.ignore_robots_txt,
            "offline": bool(args.offline),
            "refresh": bool(args.refresh),
        },
        fetched=fetched,
        earlier=earlier,
        source=source,
    )
    return OK


def check_table(table: pd.DataFrame, path: Path) -> None:
    """The table has what fetch() needs: an outlet and a url on every row, and only built-in
    outlets (C6)."""
    if "outlet" not in table.columns or "url" not in table.columns:
        found = ", ".join(map(str, table.columns)) or "none"
        raise UsageError(f"{path} needs the columns outlet and url; it has: {found}")
    blank = (table["outlet"].isna() | table["url"].isna()).tolist()
    if any(blank):
        raise UsageError(f"{path}: row {blank.index(True) + 1} has no outlet or no url")
    known = [outlet.id for outlet in builtin()]
    unknown = sorted({str(outlet) for outlet in table["outlet"]} - set(known))
    if unknown:
        raise UsageError(
            f"{path}: there's no built-in outlet {', '.join(map(repr, unknown))}; "
            f"choose from {', '.join(known)}"
        )


def scope_from(
    report: dict[str, Any] | None, path: Path
) -> tuple[tuple[str, ...], tuple[date, date] | None]:
    """The keywords and range a table's report file records, for ``trnews fetch`` (D8)."""
    if report is None:
        return (), None
    words = report.get("keywords") or []
    if not isinstance(words, list) or not all(isinstance(word, str) for word in words):
        raise UsageError(f"{path}: keywords must be a list of words")
    try:
        keywords = keywords_from(words) if words else ()
    except UsageError as error:
        raise UsageError(f"{path}: {error}") from error
    first, last = report.get("from"), report.get("to")
    if first is None and last is None:
        return keywords, None
    try:
        if not isinstance(first, str) or not isinstance(last, str):
            raise UsageError("from and to must both be days")
        return keywords, range_from(first, last)
    except UsageError as error:
        raise UsageError(
            f"{path} records the range {first!r} to {last!r}, which isn't valid"
        ) from error


def _coverage_command(args: argparse.Namespace, console: Console) -> int:
    output: Path | None = args.output
    if output is not None:
        table_format(output)
        check_writable([output], overwrite=args.overwrite)
    separator = check_separator(args, output)
    if args.check:
        check_requests(args, console)
    table = coverage(
        check=args.check,
        contact=args.contact,
        obey_robots=not args.ignore_robots_txt,
        cache_dir=args.cache_dir,
    )
    if output is None:
        sys.stdout.write(coverage_text(table) + "\n")
        sys.stdout.flush()
        return OK
    save({output: table}, separator=separator)
    console.say(f"Wrote {output} ({len(table)} outlets).")
    return OK


def coverage_text(table: pd.DataFrame) -> str:
    """``coverage()``'s table for a terminal: the short columns, then each outlet's notes and
    problems on lines of their own."""
    names = [name for name in (*COVERAGE_SHOWN, *HEALTH_SHOWN) if name in table.columns]
    columns = [[_shown(cell) for cell in cells(table[name])] for name in names]
    widths = [
        max([len(name), *map(len, shown)]) for name, shown in zip(names, columns, strict=True)
    ]
    lines = [
        "  ".join(f"{cell:<{width}}" for cell, width in zip(row, widths, strict=True)).rstrip()
        for row in [names, *zip(*columns, strict=True)]
    ]
    outlets = [str(outlet) for outlet in table["outlet"]]
    lines += ["", "Notes:"]
    lines += [f"  {outlet}: {note}" for outlet, note in zip(outlets, table["notes"], strict=True)]
    if "problems" in table.columns:
        problems = [(o, str(p)) for o, p in zip(outlets, table["problems"], strict=True) if p]
        if problems:
            lines += ["", "Problems:", *(f"  {outlet}: {text}" for outlet, text in problems)]
    return "\n".join(lines)


def _shown(cell: object) -> str:
    if cell is None:
        return ""
    if isinstance(cell, bool):
        return "yes" if cell else "no"
    return str(cell)
