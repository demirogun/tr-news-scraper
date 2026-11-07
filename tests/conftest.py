"""Shared pytest configuration: unit tests never reach the real network."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _block_real_http(request: pytest.FixtureRequest) -> None:
    """Route every ``requests`` call through ``requests_mock`` so unmocked URLs fail.

    Tests register fake responses through the ``requests_mock`` fixture. Tests marked
    ``live`` are exempt; they run only in the weekly live-check workflow.
    """
    if request.node.get_closest_marker("live") is None:
        request.getfixturevalue("requests_mock")
