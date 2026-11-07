"""What search raises when nothing could be read."""

from __future__ import annotations

from tr_news_scraper.errors import SearchFailed, TrNewsError


def test_search_failed_names_every_outlet_and_its_reason() -> None:
    failures = {
        "cumhuriyet": "its sitemap index couldn't be read: the site refused it with HTTP 403",
        "milliyet": "none of the files it needed could be read",
    }
    error = SearchFailed(failures)
    assert isinstance(error, TrNewsError)
    assert error.failures == failures
    assert str(error) == (
        "every outlet failed:\n"
        "  cumhuriyet: its sitemap index couldn't be read: the site refused it with HTTP 403\n"
        "  milliyet: none of the files it needed could be read"
    )


def test_search_failed_can_say_what_to_do_next() -> None:
    error = SearchFailed({"star": "none of the files it needed could be read"}, hint="Try again.")
    assert str(error).endswith("could be read\nTry again.")
