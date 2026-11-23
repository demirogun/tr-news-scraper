"""How the live check treats sites that refuse GitHub's runners: offline, without a request."""

from __future__ import annotations

import pytest

from tests.live import networks
from tr_news_scraper.errors import Blocked, OutletFailed
from tr_news_scraper.outlets import builtin

REFUSED_INDEX = f"its sitemap index couldn't be read: {networks.REFUSED}"


def failure(status: int) -> OutletFailed:
    """The failure a scan raises when the site refuses its index with ``status``."""
    try:
        try:
            raise Blocked("https://www.odatv.com/categories.xml", status)
        except Blocked as error:
            raise OutletFailed("odatv", "its sitemap index couldn't be read") from error
    except OutletFailed as raised:
        return raised


def test_on_github_only_a_listed_outlets_403_counts_as_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(networks, "ON_GITHUB", True)
    assert networks.refused_on_github("odatv", failure(403))
    assert not networks.refused_on_github("odatv", failure(451))
    assert not networks.refused_on_github("star", failure(403))
    assert not networks.refused_on_github("odatv", OutletFailed("odatv", "no files"))


def test_elsewhere_nothing_counts_as_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(networks, "ON_GITHUB", False)
    assert not networks.refused_on_github("odatv", failure(403))
    assert not networks.problems_refused_on_github("odatv", (REFUSED_INDEX,))


def test_a_health_check_counts_as_refused_only_when_every_problem_is_the_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(networks, "ON_GITHUB", True)
    assert networks.REFUSED == "the site refused it with HTTP 403"
    assert networks.problems_refused_on_github("turkgun", (REFUSED_INDEX,))
    assert not networks.problems_refused_on_github("turkgun", (REFUSED_INDEX, "no entries"))
    assert not networks.problems_refused_on_github("turkgun", ())
    assert not networks.problems_refused_on_github("sabah", (REFUSED_INDEX,))


def test_the_listed_outlets_are_built_in() -> None:
    assert {outlet.id for outlet in builtin(include_opt_in=True)} >= networks.REFUSE_GITHUB
    assert "www.odatv.com" in networks.hosts_refusing_github()
