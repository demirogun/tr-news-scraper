"""scripts/check_dist.py: built archives hold only what we mean to ship."""

from __future__ import annotations

import importlib.util
import io
import tarfile
import zipfile
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_dist.py"
ENTRY_POINTS = "tr_news_scraper-1.0.0.dist-info/entry_points.txt"
GOOD_WHEEL = [
    "tr_news_scraper/__init__.py",
    "tr_news_scraper-1.0.0.dist-info/METADATA",
    ENTRY_POINTS,
]
TRNEWS = """[console_scripts]
trnews = tr_news_scraper._cli:main
"""
GOOD_SDIST = [
    "tr_news_scraper-1.0.0/pyproject.toml",
    "tr_news_scraper-1.0.0/src/tr_news_scraper/__init__.py",
]


def load_checker() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_dist", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_dist(
    tmp_path: Path, wheel_names: list[str], sdist_names: list[str], *, entry_points: str = TRNEWS
) -> Path:
    dist = tmp_path / "dist"
    dist.mkdir()
    with zipfile.ZipFile(dist / "tr_news_scraper-1.0.0-py3-none-any.whl", "w") as wheel:
        for name in wheel_names:
            wheel.writestr(name, entry_points if name == ENTRY_POINTS else "x")
    with tarfile.open(dist / "tr_news_scraper-1.0.0.tar.gz", "w:gz") as sdist:
        for name in sdist_names:
            info = tarfile.TarInfo(name)
            info.size = 1
            sdist.addfile(info, io.BytesIO(b"x"))
    return dist


def test_clean_archives_have_no_problems(tmp_path: Path) -> None:
    dist = make_dist(tmp_path, GOOD_WHEEL, GOOD_SDIST)
    assert load_checker().problems(dist) == []


def test_a_wheel_with_files_outside_the_package_is_reported(tmp_path: Path) -> None:
    dist = make_dist(tmp_path, [*GOOD_WHEEL, "tests/test_package.py"], GOOD_SDIST)
    found = load_checker().problems(dist)
    assert len(found) == 1
    assert "tests/test_package.py" in found[0]


@pytest.mark.parametrize(
    "planning_doc",
    ["SPEC.md", "SPEC-http.md", "docs/ideas/one-pager.md", "docs/intent/x.md", "tasks/plan.md"],
)
def test_planning_docs_in_the_sdist_are_reported(tmp_path: Path, planning_doc: str) -> None:
    dist = make_dist(tmp_path, GOOD_WHEEL, [*GOOD_SDIST, f"tr_news_scraper-1.0.0/{planning_doc}"])
    found = load_checker().problems(dist)
    assert len(found) == 1
    assert planning_doc in found[0]


def test_a_dist_folder_without_both_archives_is_reported(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    assert load_checker().problems(dist) == [f"expected a wheel and an sdist in {dist}"]


def test_main_exits_nonzero_when_problems_are_found(tmp_path: Path) -> None:
    dist = make_dist(tmp_path, [*GOOD_WHEEL, "extra.txt"], GOOD_SDIST)
    assert load_checker().main(["check_dist.py", str(dist)]) == 1


def test_main_exits_zero_for_clean_archives(tmp_path: Path) -> None:
    dist = make_dist(tmp_path, GOOD_WHEEL, GOOD_SDIST)
    assert load_checker().main(["check_dist.py", str(dist)]) == 0


NO_TRNEWS = (
    "tr_news_scraper-1.0.0-py3-none-any.whl: no trnews command "
    "(console_scripts entry point tr_news_scraper._cli:main)"
)


def test_a_wheel_without_entry_points_is_reported(tmp_path: Path) -> None:
    wheel = [name for name in GOOD_WHEEL if name != ENTRY_POINTS]
    dist = make_dist(tmp_path, wheel, GOOD_SDIST)
    assert load_checker().problems(dist) == [NO_TRNEWS]


@pytest.mark.parametrize(
    "entry_points",
    [
        "[console_scripts]\ntrnews = tr_news_scraper.cli:main\n",
        "[gui_scripts]\ntrnews = tr_news_scraper._cli:main\n",
        "[console_scripts]\nnews = tr_news_scraper._cli:main\n",
    ],
)
def test_a_wheel_whose_trnews_is_wrong_is_reported(tmp_path: Path, entry_points: str) -> None:
    dist = make_dist(tmp_path, GOOD_WHEEL, GOOD_SDIST, entry_points=entry_points)
    assert load_checker().problems(dist) == [NO_TRNEWS]
