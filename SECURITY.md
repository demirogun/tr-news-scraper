# Security policy

## Supported versions

| Version | Supported |
|---|---|
| 1.x | Yes |
| 0.1.x | No. 0.1.0 pins dependencies with known vulnerabilities; please upgrade. |

## Reporting a vulnerability

Please report security problems privately, not in a public issue. On GitHub, open the repository's
**Security** tab and choose **Report a vulnerability**:
https://github.com/demirogun/tr-news-scraper/security/advisories/new

Include the affected version, what an attacker could do, and steps or a proof of concept to
reproduce it. We'll confirm we received your report, keep you updated while we work on a fix, and
credit you in the release notes unless you'd rather stay anonymous.

## What the library does to stay safe

- Every request goes to an HTTPS page on a host the outlet allows. Redirects are checked again at
  every hop, and URLs that name private or reserved network addresses are refused.
- XML from websites is parsed with entity expansion, DTD loading and network access turned off.
- Response sizes are capped after decompression, so a compression bomb is stopped early.
- Requests are stateless: no cookies are stored or sent.

## Dependencies

CI audits every locked dependency for known vulnerabilities and fails if one is found. Dependabot
proposes dependency and GitHub Actions updates weekly.
