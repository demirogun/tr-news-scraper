"""CITATION.cff cites the newest dated release, by the authors pyproject.toml names (release)."""

from __future__ import annotations

import re
import tomllib
from importlib.metadata import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASED = re.compile(r"^## \[(?P<version>[^\]]+)\] - (?P<date>\d{4}-\d{2}-\d{2})$", re.MULTILINE)
CONCEPT_DOI = "10.5281/zenodo.10509649"


def citation() -> str:
    return (ROOT / "CITATION.cff").read_text(encoding="utf-8")


def field(name: str) -> str:
    """A top-level ``name: value`` of CITATION.cff, without quotes."""
    found = re.search(rf'^{re.escape(name)}: "?([^"\n]+?)"?$', citation(), re.MULTILINE)
    assert found, f"CITATION.cff has no {name}"
    return found.group(1)


def test_it_cites_the_newest_dated_release_in_the_changelog() -> None:
    newest = RELEASED.search((ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))
    assert newest is not None
    assert (field("version"), field("date-released")) == (newest["version"], newest["date"])


def test_its_authors_are_pyprojects_with_turkish_letters() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    given = re.findall(r"^  - given-names: (.+)$", citation(), re.MULTILINE)
    family = re.findall(r"^    family-names: (.+)$", citation(), re.MULTILINE)
    names = [f"{first} {last}" for first, last in zip(given, family, strict=True)]
    assert names == [author["name"] for author in project["authors"]]
    assert names == ["Ogün Demir", "Aydoğan Avcıoğlu"]


def test_it_has_the_concept_doi_the_license_and_the_repository() -> None:
    assert field("cff-version") == "1.2.0"
    assert field("type") == "software"
    assert field("doi") == CONCEPT_DOI
    assert field("license") == "MIT"
    assert field("repository-code") == "https://github.com/demirogun/tr-news-scraper"


def test_the_package_metadata_points_to_the_citation_and_is_stable() -> None:
    found = metadata("tr-news-scraper")
    urls = dict(url.split(", ", 1) for url in found.get_all("Project-URL") or [])
    assert urls["Citation"] == f"https://doi.org/{CONCEPT_DOI}"
    assert set(urls) == {"Documentation", "Source", "Changelog", "Issues", "Citation"}
    classifiers = found.get_all("Classifier") or []
    assert "Development Status :: 5 - Production/Stable" in classifiers
    assert "Environment :: Console" in classifiers
