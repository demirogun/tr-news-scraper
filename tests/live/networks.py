"""Sites that refuse GitHub's runners, and how the live check treats them there.

On 2026-11-24 five outlets answered the weekly check's requests from GitHub's runners with
HTTP 403 (run 45270984029), while the same requests from a network in Türkiye, through the same
client and User-Agent, were read. On GitHub, those refusals are skipped and named in the log;
anywhere else, these outlets are checked in full. Any other failure still fails.
"""

from __future__ import annotations

import os

from tr_news_scraper.errors import Blocked
from tr_news_scraper.outlets import get
from tr_news_scraper.outlets._scan import describe

REFUSE_GITHUB = frozenset({"aydinlik", "haber-global", "odatv", "ozgur-kocaeli", "turkgun"})
"""The outlets whose sites refuse GitHub's runners with HTTP 403."""
ON_GITHUB = os.environ.get("GITHUB_ACTIONS") == "true"
REFUSED = describe(Blocked("https://example.com.tr/", 403))
"""How a health check words that refusal."""


def refused_on_github(outlet_id: str, error: BaseException | None) -> bool:
    """Whether a failure is one of those sites refusing GitHub's runner with HTTP 403."""
    if not (ON_GITHUB and outlet_id in REFUSE_GITHUB):
        return False
    while error is not None:
        if isinstance(error, Blocked) and error.status == 403:
            return True
        error = error.__cause__
    return False


def problems_refused_on_github(outlet_id: str, problems: tuple[str, ...]) -> bool:
    """Whether every problem a health check found is that refusal, on GitHub."""
    if not (ON_GITHUB and outlet_id in REFUSE_GITHUB):
        return False
    return bool(problems) and all(problem.endswith(REFUSED) for problem in problems)


def hosts_refusing_github() -> frozenset[str]:
    """Every host of those outlets."""
    return frozenset(host for outlet_id in REFUSE_GITHUB for host in get(outlet_id).hosts)
