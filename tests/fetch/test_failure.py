"""What fetch raises when no article could be read."""

from __future__ import annotations

from tr_news_scraper.errors import FetchFailed, TrNewsError


def test_fetch_failed_names_every_outlets_reason() -> None:
    failures = {
        "star": "robots.txt disallows it",
        "milliyet": "the site refused it with HTTP 403",
    }
    error = FetchFailed(failures)
    assert isinstance(error, TrNewsError)
    assert error.failures == failures
    assert str(error) == (
        "no article could be read:\n"
        "  star: robots.txt disallows it\n"
        "  milliyet: the site refused it with HTTP 403"
    )


def test_fetch_failed_can_say_what_to_do_next() -> None:
    error = FetchFailed({"star": "not in the cache (offline mode)"}, hint="Fetch once online.")
    assert str(error).endswith("(offline mode)\nFetch once online.")
