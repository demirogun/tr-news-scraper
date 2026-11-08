"""scripts/release.py: a tag agrees with the files that describe its release (release, R3)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = """# Changelog

## [Unreleased]

## [1.0.0] - 2026-11-20

### Added
- `search()`, the new way to find news.

## [0.1.0] - 2024-01-10

### Added
- First release.

[Unreleased]: https://github.com/demirogun/tr-news-scraper/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/demirogun/tr-news-scraper/compare/v0.1.0...v1.0.0
[0.1.0]: https://github.com/demirogun/tr-news-scraper/releases/tag/v0.1.0
"""
CITATION = (
    'cff-version: 1.2.0\ntitle: tr-news-scraper\nversion: "1.0.0"\ndate-released: "2026-11-20"\n'
)


def load_release() -> ModuleType:
    spec = importlib.util.spec_from_file_location("release", ROOT / "scripts" / "release.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def project(
    root: Path, version: str = "1.0.0", changelog: str = CHANGELOG, citation: str = CITATION
) -> Path:
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "tr-news-scraper"\nversion = "{version}"\n', encoding="utf-8"
    )
    (root / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
    (root / "CITATION.cff").write_text(citation, encoding="utf-8")
    return root


def test_a_final_release_whose_files_agree_has_no_problems(tmp_path: Path) -> None:
    assert load_release().check("v1.0.0", project(tmp_path)) == []


def test_the_tag_must_be_v_and_pyprojects_version(tmp_path: Path) -> None:
    assert load_release().check("v1.0.1", project(tmp_path)) == [
        "the tag v1.0.1 isn't v1.0.0, the version in pyproject.toml"
    ]


@pytest.mark.parametrize("version", ["1.0", "1.0.0.dev0", "1.0.0.post1", "1.0.0-rc1", "01.0.0"])
def test_only_final_and_pre_release_versions_can_be_released(tmp_path: Path, version: str) -> None:
    found = load_release().check(f"v{version}", project(tmp_path, version=version))
    assert found == [
        f"pyproject.toml: {version} isn't a version to release, such as 1.0.0 or 1.0.0rc1"
    ]


@pytest.mark.parametrize("version", ["1.0.0rc1", "1.1.0a2", "2.0.0b1"])
def test_a_pre_release_needs_no_changelog_section_or_citation(tmp_path: Path, version: str) -> None:
    root = project(tmp_path, version=version, changelog="# Changelog\n", citation="")
    assert load_release().check(f"v{version}", root) == []


@pytest.mark.parametrize(
    ("changelog", "problem"),
    [
        (
            CHANGELOG.replace("## [1.0.0] - 2026-11-20", "## [1.1.0] - 2026-11-20"),
            "CHANGELOG.md: there's no section for 1.0.0",
        ),
        (
            CHANGELOG.replace("## [1.0.0] - 2026-11-20", "## [1.0.0]"),
            "CHANGELOG.md: the 1.0.0 section has no date",
        ),
        (
            CHANGELOG.replace("[1.0.0]: https://", "[1.0]: https://"),
            "CHANGELOG.md: there's no [1.0.0] link at the end",
        ),
    ],
)
def test_a_final_release_needs_a_dated_changelog_section_and_its_link(
    tmp_path: Path, changelog: str, problem: str
) -> None:
    found = load_release().check("v1.0.0", project(tmp_path, changelog=changelog))
    assert problem in found


@pytest.mark.parametrize(
    ("citation", "problem"),
    [
        (CITATION.replace('"1.0.0"', '"0.1.0"'), "CITATION.cff: version is 0.1.0, not 1.0.0"),
        (
            CITATION.replace("2026-11-20", "2026-11-19"),
            "CITATION.cff: date-released is 2026-11-19, not the CHANGELOG's 2026-11-20",
        ),
        ("cff-version: 1.2.0\n", "CITATION.cff: version is missing, not 1.0.0"),
    ],
)
def test_a_final_release_needs_citation_cff_to_cite_it(
    tmp_path: Path, citation: str, problem: str
) -> None:
    assert problem in load_release().check("v1.0.0", project(tmp_path, citation=citation))


def test_notes_are_exactly_the_versions_changelog_section(tmp_path: Path) -> None:
    release, root = load_release(), project(tmp_path)
    assert release.notes("1.0.0", root) == "### Added\n- `search()`, the new way to find news.\n"
    assert release.notes("0.1.0", root) == "### Added\n- First release.\n"
    with pytest.raises(ValueError, match=r"CHANGELOG\.md: there's no section for 2\.0\.0"):
        release.notes("2.0.0", root)


def test_main_checks_prints_notes_and_explains_its_usage(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    release, root = load_release(), project(tmp_path)
    assert release.main(["release.py", "check", "v1.0.0"], root=root) == 0
    assert (
        capsys.readouterr().out
        == "v1.0.0 agrees with pyproject.toml, CHANGELOG.md and CITATION.cff\n"
    )
    assert release.main(["release.py", "check", "v9.0.0"], root=root) == 1
    assert "the tag v9.0.0 isn't v1.0.0" in capsys.readouterr().err
    assert release.main(["release.py", "notes", "1.0.0"], root=root) == 0
    assert capsys.readouterr().out.startswith("### Added\n")
    assert release.main(["release.py", "notes", "2.0.0"], root=root) == 1
    assert release.main(["release.py", "publish"], root=root) == 2
    assert "usage: release.py check TAG | notes VERSION" in capsys.readouterr().err


def test_the_repositorys_own_changelog_has_0_1_0s_notes() -> None:
    assert load_release().notes("0.1.0", ROOT).startswith("### Added\n- First release:")


def test_the_repositorys_own_version_is_ready_to_tag() -> None:
    release = load_release()
    version = release.project_version(ROOT)
    assert release.check(f"v{version}", ROOT) == []
