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

Security researchers who have contributed to RedWire's security posture are listed here.

### 2026-05 coordinated disclosure — Lockheed Martin Red Team

Nineteen advisories reported by **HackAndPwn** at the Lockheed Martin Red Team through GitHub's coordinated disclosure flow. Each report included a complete write-up with proof-of-concept and, in most cases, a suggested fix — depth of analysis that made the maintainer-side patches reviewable and fast to land. Fixes shipped in v1.1.0.

| Advisory | Summary |
|---|---|
| GHSA-39x9-f79h-rh4r | Login handler does not bind credentials to their auth provider |
| GHSA-68hx-hggg-vrr2 | SAML ACS accepts unsolicited responses, runs when SAML is disabled, and adopts existing local accounts by name |
| GHSA-p97c-94pr-2m32 | Logout blacklists access token only — refresh token survives and mints new sessions |
| GHSA-vm6w-9wm5-q367 | 2FA enrollment requires no password |
| GHSA-7rcx-8hqc-mm5f | API tokens survive password change and global session revocation |
| GHSA-hc9w-hggj-r52w | Email change requires no password |
| GHSA-xfrh-8gq5-f82x | WebSocket endpoints lack token-type and engagement-membership checks |
| GHSA-m8mm-g4rr-cwph | Secondary-FK link endpoints do not scope the linked resource to the primary's engagement |
| GHSA-438x-7v7q-hpj9 | Test-case version-history endpoints lack engagement-membership check |
| GHSA-ffmc-hrp8-hhj7 | Analytics and stats aggregate-read endpoints lack engagement scoping |
| GHSA-74g3-5fmp-7p85 | Engagement import allows cross-tenant record injection and attribution forgery |
| GHSA-58q3-f33p-w84m | Per-item infra-vault ACL grant/revoke reachable by any grantee |
| GHSA-6vmm-vfh3-6p5r | Vault credential edits leak plaintext in logs and on update |
| GHSA-qf2j-p8q7-v98h | MCP server /sse has no authentication and falls back to a service-scope token |
| GHSA-vm9w-7vpv-2jpm | PDF report generator passes user fields to ReportLab Paragraph() unescaped — SSRF + local file read |
| GHSA-3gpw-vj2h-2x25 | Markdown image upload accepts SVG and serves it inline — stored XSS |
| GHSA-ghw9-87v2-9453 | Scanner-import XML parsed without defusedxml — entity-expansion DoS |
| GHSA-wr3h-qrm5-x433 | Arbitrary file deletion via profile_photo path |
| GHSA-x64x-c7pw-7g8x | API token can mint its own non-expiring replacement |

## Out of scope

The following are known properties of the current design and are not treated as vulnerabilities unless the underlying threat model changes:

- **JWT tokens stored in `localStorage`.** This is intentional in the current design. Reports specifically about token storage location will not be treated as vulnerabilities; reports about the underlying token handling (signing, expiry, refresh logic) are in scope.
- **Default admin credentials (`admin` / `changeme`).** Operators are expected to change these on first login; this is documented in the README.
- **Issues that require a privileged operator role to exploit** are generally lower priority, since users with admin or team-lead roles already have broad access by design. Privilege-escalation issues that allow a lower role to gain a higher one are in scope.
