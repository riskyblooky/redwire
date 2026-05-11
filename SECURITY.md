# Security Policy

RedWire is maintained by a single developer. Security reports are taken seriously and acknowledged publicly where appropriate.

## Supported versions

Only the latest release on the `main` branch is supported. Fixes are applied to `main` and shipped in the next release; older versions do not receive backports.

## Reporting a vulnerability

There are two paths, depending on the severity of the issue:

**For sensitive vulnerabilities** (anything that could compromise a live deployment — authentication bypass, RCE, SQL injection, vault decryption, IDOR exposing other tenants' data, etc.):

Please use GitHub's private vulnerability reporting feature on this repository ("Security" tab → "Report a vulnerability"). This keeps the report private until a fix is published.

**For lower-impact issues** (hardening suggestions, missing rate limits, defense-in-depth gaps, dependency advisories without a known exploit):

Open a regular GitHub issue with the `security` label.

When reporting, please include:

- A description of the issue and its impact.
- Steps to reproduce, ideally with a minimal proof of concept.
- The affected version or commit hash.
- Any suggested remediation, if you have one in mind.

## What to expect

- An initial acknowledgement within a few days. This is a side project, so response times are best-effort, not contractual.
- A follow-up with a triage decision (accepted, needs more info, won't fix) once the report has been reviewed.
- For accepted reports, a fix landed on `main` and a public advisory describing the issue and the fix.

## No bug bounty

There is no monetary bounty program. RedWire is a personal project with no revenue behind it.

What is offered instead:

- Public credit in the release notes for the fix.
- A line in the acknowledgements section below (opt-in — let me know how you would like to be credited, or whether you would prefer to remain anonymous).
- A reference to your report in the GitHub Security Advisory, which makes it part of the public CVE record if a CVE is assigned.

## Acknowledgements

Security researchers who have contributed to RedWire's security posture will be listed here.

*No reports yet — this section will be populated as reports come in.*

## Out of scope

The following are known properties of the current design and are not treated as vulnerabilities unless the underlying threat model changes:

- **JWT tokens stored in `localStorage`.** This is intentional in the current design. Reports specifically about token storage location will not be treated as vulnerabilities; reports about the underlying token handling (signing, expiry, refresh logic) are in scope.
- **Default admin credentials (`admin` / `changeme`).** Operators are expected to change these on first login; this is documented in the README.
- **Issues that require a privileged operator role to exploit** are generally lower priority, since users with admin or team-lead roles already have broad access by design. Privilege-escalation issues that allow a lower role to gain a higher one are in scope.
