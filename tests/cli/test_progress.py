"""trnews on a terminal and off it: the status line, -q and -v, and encodings (C7, C8)."""

from __future__ import annotations

import io
import logging
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.cli.conftest import Library, fetch_result, search_result
from tr_news_scraper import FetchResult, SearchResult
from tr_news_scraper._cli import Console, Tracker, main

SEARCH = ["search", "deprem", "tsunami", "--from", "2023-02-01", "--to", "2023-02-28"]
NAMES = {"aksam": "Akşam", "star": "Star"}


class FakeTerminal(io.StringIO):
    def isatty(self) -> bool:
        return True


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_the_status_line_is_redrawn_in_place_below_messages() -> None:
    stream = FakeTerminal()
    console = Console(stream, width=lambda: 80)
    first, second = "Reading 3 articles: Akşam 1/1", "Reading 3 articles: Star 1/2"
    console.status(first)
    console.status(second)
    console.write("  Star: 2 articles read")
    console.end_status()
    erase = "\r" + " " * len(second) + "\r"
    assert stream.getvalue() == (
        f"\r{first}\r{second} {erase}  Star: 2 articles read\n{second}{erase}"
    )
    assert console.shown == ""


def test_a_long_status_line_is_cut_to_the_terminal_width() -> None:
    console = Console(FakeTerminal(), width=lambda: 20)
    console.status("Reading 7,612 articles: Cumhuriyet 120/2,190")
    assert console.shown == "Reading 7,612 arti…"


def test_there_is_no_status_line_off_a_terminal_or_when_quiet() -> None:
    stream = io.StringIO()
    console = Console(stream)
    console.status("Reading 3 articles")
    console.end_status()
    assert (console.live, stream.getvalue()) == (False, "")
    assert not Console(FakeTerminal(), quiet=True).live


def test_the_tracker_shows_each_outlet_and_estimates_the_time_left() -> None:
    console, clock = Console(FakeTerminal(), width=lambda: 200), Clock()
    tracker = Tracker(6, console, NAMES, clock=clock)
    tracker.update("aksam", 1, 2)
    assert console.shown == "Reading 6 articles: Akşam 1/2"
    clock.now = 4.0
    tracker.update("star", 1, 4)
    assert console.shown == "Reading 6 articles: Akşam 1/2 · Star 1/4"
    clock.now = 10.0
    tracker.update("star", 2, 4)
    assert console.shown == "Reading 6 articles: Akşam 1/2 · Star 2/4 · about 10 s left"
    assert tracker.done == 3


def test_the_tracker_redraws_four_times_a_second_but_always_at_an_outlets_end() -> None:
    console, clock = Console(FakeTerminal(), width=lambda: 200), Clock()
    tracker = Tracker(3, console, NAMES, clock=clock)
    tracker.update("star", 1, 3)
    clock.now = 0.1
    tracker.update("star", 2, 3)
    assert console.shown == "Reading 3 articles: Star 1/3"
    clock.now = 0.2
    tracker.update("star", 3, 3)
    assert console.shown == "Reading 3 articles: Star 3/3"


def reading(progress: Any) -> FetchResult:
    """A stand-in fetch that reports progress the way fetch() does."""
    log = logging.getLogger("tr_news_scraper.fetch")
    log.info("Star: 100 of 200 articles read, about 2 min left", extra={"progress": True})
    progress("star", 1, 1)
    log.info("Star: 1 articles read: 1 downloaded, 0 from the cache, 0 failed")
    return fetch_result()


def test_on_a_terminal_fetch_shows_a_status_line_instead_of_progress_lines(
    library: Library, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    terminal = FakeTerminal()
    monkeypatch.setattr(sys, "stderr", terminal)
    library.on_fetch = reading
    assert main([*SEARCH, "--fetch", "-o", str(tmp_path / "found.csv")]) == 0
    shown = terminal.getvalue()
    assert "\rReading 3 articles: Star 1/1" in shown
    assert "about 2 min left" not in shown
    assert "  Star: 1 articles read: 1 downloaded, 0 from the cache, 0 failed\n" in shown
    assert shown.endswith(f" and {tmp_path / 'found.report.json'}.\n")


def test_off_a_terminal_fetch_shows_the_librarys_progress_lines(
    library: Library, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    library.on_fetch = reading
    assert main([*SEARCH, "--fetch", "-o", str(tmp_path / "found.csv")]) == 0
    shown = capsys.readouterr().err
    assert "\n  Star: 100 of 200 articles read, about 2 min left\n" in shown
    assert "\r" not in shown


def test_verbose_adds_the_librarys_other_lines(
    library: Library, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def noisy() -> SearchResult:
        logging.getLogger("tr_news_scraper.outlets").info("Star: 2 month(s) not read")
        return search_result()

    library.on_search = noisy
    path = str(tmp_path / "found.csv")
    assert main([*SEARCH, "-o", path]) == 0
    assert "month(s) not read" not in capsys.readouterr().err
    assert main([*SEARCH, "-o", path, "--overwrite", "-v"]) == 0
    assert "\n  Star: 2 month(s) not read\n" in capsys.readouterr().err


def cp1252(errors: str) -> tuple[io.BytesIO, io.TextIOWrapper]:
    """A stream like a redirected Windows console's on Python 3.12–3.14."""
    raw = io.BytesIO()
    return raw, io.TextIOWrapper(raw, encoding="cp1252", errors=errors)


def test_a_cp1252_standard_error_shows_letters_it_lacks_as_question_marks(
    library: Library, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw, stream = cp1252("backslashreplace")
    monkeypatch.setattr(sys, "stderr", stream)
    assert main([*SEARCH, "-o", str(tmp_path / "found.csv")]) == 0
    stream.flush()
    shown = raw.getvalue().decode("cp1252")
    assert "\n  Ak?am  1" in shown
    assert "Sözcü" in shown


def test_a_cp1252_standard_output_prints_the_coverage_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw, stream = cp1252("strict")
    monkeypatch.setattr(sys, "stdout", stream)
    assert main(["coverage"]) == 0
    stream.flush()
    assert "\naksam        Ak?am " in raw.getvalue().decode("cp1252")
