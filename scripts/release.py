"""Check a release tag against the files that describe the release, and print its notes.

The release workflow runs both before anything is published::

    uv run python scripts/release.py check v1.0.0     # the tag, pyproject.toml, CHANGELOG.md
                                                      # and CITATION.cff agree
    uv run python scripts/release.py notes 1.0.0      # the GitHub release's notes

A pre-release such as ``1.0.0rc1`` goes to PyPI only, so only its tag is checked.
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "https://github.com/demirogun/tr-news-scraper"
RELEASABLE = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)((a|b|rc)(0|[1-9]\d*))?")
FINAL = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)")
LINK = re.compile(r"^\[[^\]]+\]: https?://\S+$", re.MULTILINE)
USAGE = "usage: release.py check TAG | notes VERSION"


def project_version(root: Path) -> str:
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    return str(project["version"])


def section(changelog: str, version: str) -> tuple[str | None, str] | None:
    """The date and the body of ``version``'s CHANGELOG section; ``None`` if it has none."""
    heading = re.compile(
        rf"^## \[{re.escape(version)}\](?: - (\d{{4}}-\d{{2}}-\d{{2}}))?[ \t]*$", re.MULTILINE
    )
    found = heading.search(changelog)
    if found is None:
        return None
    rest = changelog[found.end() :]
    following = re.search(r"^## \[", rest, re.MULTILINE)
    body = rest if following is None else rest[: following.start()]
    return found.group(1), LINK.sub("", body).strip()


def cited(root: Path) -> dict[str, str]:
    """CITATION.cff's top-level ``key: value`` lines, without quotes."""
    path = root / "CITATION.cff"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    return {
        found[1]: found[2]
        for found in re.finditer(r'^([a-z-]+): "?([^"\n]*?)"?[ \t]*$', text, re.MULTILINE)
    }


def check(tag: str, root: Path) -> list[str]:
    """Every way ``tag`` disagrees with pyproject.toml, CHANGELOG.md and CITATION.cff."""
    version = project_version(root)
    if not RELEASABLE.fullmatch(version):
        return [f"pyproject.toml: {version} isn't a version to release, such as 1.0.0 or 1.0.0rc1"]
    if tag != f"v{version}":
        return [f"the tag {tag} isn't v{version}, the version in pyproject.toml"]
    if not FINAL.fullmatch(version):
        return []
    problems: list[str] = []
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    found = section(changelog, version)
    date = None if found is None else found[0]
    if found is None:
        problems.append(f"CHANGELOG.md: there's no section for {version}")
    elif date is None:
        problems.append(f"CHANGELOG.md: the {version} section has no date")
    if not re.search(rf"^\[{re.escape(version)}\]: {re.escape(REPOSITORY)}/", changelog, re.M):
        problems.append(f"CHANGELOG.md: there's no [{version}] link at the end")
    citation = cited(root)
    if citation.get("version") != version:
        problems.append(
            f"CITATION.cff: version is {citation.get('version', 'missing')}, not {version}"
        )
    if date is not None and citation.get("date-released") != date:
        problems.append(
            f"CITATION.cff: date-released is {citation.get('date-released', 'missing')}, "
            f"not the CHANGELOG's {date}"
        )
    return problems


def notes(version: str, root: Path) -> str:
    """``version``'s CHANGELOG section, without its heading: the GitHub release's notes."""
    found = section((root / "CHANGELOG.md").read_text(encoding="utf-8"), version)
    if found is None:
        raise ValueError(f"CHANGELOG.md: there's no section for {version}")
    return found[1] + "\n"


def main(argv: list[str], root: Path = ROOT) -> int:
    """Run ``check TAG`` or ``notes VERSION``; return 0, 1 for a problem, or 2 for bad usage."""
    if len(argv) != 3 or argv[1] not in {"check", "notes"}:
        print(USAGE, file=sys.stderr)
        return 2
    command, value = argv[1], argv[2]
    if command == "check":
        problems = check(value, root)
        for problem in problems:
            print(problem, file=sys.stderr)
        if problems:
            return 1
        print(f"{value} agrees with pyproject.toml, CHANGELOG.md and CITATION.cff")
        return 0
    try:
        sys.stdout.write(notes(value, root))
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
