"""Opt-in outlets: built in, but read only when named (SPEC-1.1 P4)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import tr_news_scraper.outlets._builtin as builtin_module
from tr_news_scraper import coverage
from tr_news_scraper._cli import check_table, coverage_text, outlets_from
from tr_news_scraper._fetch import _inputs
from tr_news_scraper._search import resolve_outlets
from tr_news_scraper.outlets import MonthlySitemap, builtin, get

EXTRA = MonthlySitemap(
    id="ornek-ajans",
    name="Örnek Ajans",
    index="https://www.example.com.tr/sitemap.xml",
    month_file=r"/sitemap-(?P<year>\d{4})-(?P<month>\d{2})\.xml$",
    notes="Opt-in.",
)


@pytest.fixture
def opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(builtin_module, "OPT_IN", (EXTRA,))


def rows(*outlets: str) -> pd.DataFrame:
    urls = [f"https://www.example.com.tr/haber-{n}" for n in range(len(outlets))]
    return pd.DataFrame({"outlet": list(outlets), "url": urls}, dtype="string")


@pytest.mark.usefixtures("opt_in")
def test_builtin_gives_the_defaults_and_on_request_the_opt_in_outlets_last() -> None:
    assert EXTRA not in builtin()
    assert builtin(include_opt_in=True) == (*builtin(), EXTRA)


@pytest.mark.usefixtures("opt_in")
def test_get_finds_an_opt_in_outlet_and_names_every_id() -> None:
    assert get("ornek-ajans") is EXTRA
    with pytest.raises(ValueError, match=r"choose from cumhuriyet, .*, milliyet, ornek-ajans$"):
        get("yok")


@pytest.mark.usefixtures("opt_in")
def test_coverage_lists_opt_in_outlets_last_and_not_as_defaults() -> None:
    table = coverage()
    assert list(table["outlet"]) == [outlet.id for outlet in (*builtin(), EXTRA)]
    assert table["default"].tolist() == [True] * len(builtin()) + [False]
    assert coverage_text(table).splitlines()[len(builtin()) + 1].split()[-1] == "no"


def test_an_outlet_of_your_own_isnt_a_default() -> None:
    assert coverage([EXTRA])["default"].tolist() == [False]


@pytest.mark.usefixtures("opt_in")
def test_search_reads_an_opt_in_outlet_only_when_named() -> None:
    assert EXTRA not in resolve_outlets(None)
    assert resolve_outlets([*builtin(), "ornek-ajans"])[-1] is EXTRA


@pytest.mark.usefixtures("opt_in")
def test_fetch_says_how_to_include_an_opt_in_outlet() -> None:
    hint = r"opt-in built-in outlet: pass outlets=builtin\(include_opt_in=True\)"
    with pytest.raises(ValueError, match=hint):
        _inputs(rows("star", "ornek-ajans"), None, None, None, None)
    chosen = _inputs(rows("ornek-ajans"), None, None, None, builtin(include_opt_in=True))[4]
    assert EXTRA in chosen
    with pytest.raises(ValueError, match=r"no outlet definition for baska; pass it in outlets$"):
        _inputs(rows("baska"), None, None, None, None)


@pytest.mark.usefixtures("opt_in")
def test_the_command_line_takes_opt_in_ids(tmp_path: Path) -> None:
    assert outlets_from("star,ornek-ajans") == ("star", "ornek-ajans")
    check_table(rows("star", "ornek-ajans"), tmp_path / "haberler.csv")
