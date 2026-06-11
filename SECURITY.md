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

### 2026-05 / 2026-06 follow-up disclosure batch — Lockheed Martin Red Team

A second wave of forty-three advisories reported by **HackAndPwn** at the Lockheed Martin Red Team between the v1.1.0 release and the v1.2.0 cut. Same operating model as the v1.1.0 batch: each report included a complete write-up, a working proof-of-concept, and a suggested fix shape, which made every maintainer-side patch reviewable and most of them mergeable in a single review pass. Fixes shipped in v1.2.0.

| Advisory | Summary |
|---|---|
| GHSA-287x-h6p3-frfv | Evidence on VERIFIED findings can be replaced or deleted — chain-of-custody bypass |
| GHSA-28f5-4wcg-9pwv | Startup seeders re-grant revoked permissions and re-promote demoted admins |
| GHSA-2gmw-jf4c-8q5g | COMPLETED engagements modifiable by non-admin operators |
| GHSA-2hrj-c2v3-8p2v | Username field lacks Unicode normalization and charset allowlist — homograph identity collision |
| GHSA-2rv7-jv5j-m4jg | Plugin routes mounted without enforced authentication; plugin directories prepended to module search path |
| GHSA-3m9c-7f84-9cm2 | Any Team Lead can seize the platform default report theme |
| GHSA-3mpw-xmrg-5rx5 | Cascade test-case delete bypasses TESTCASE_DELETE_ANY permission on descendants |
| GHSA-3r7j-7h5r-gxgx | Vault encryption-at-rest not applied on engagement import/export |
| GHSA-464j-7qr3-47pj | Insufficient session expiration after privilege change; WebSocket handlers trust stale JWT claims |
| GHSA-4jrh-3m3r-p448 | Disabling a plugin leaves its API routes mounted and serving requests |
| GHSA-4m4r-qhpf-5r8x | Asset import lacks size and row limits — unbounded upload causes worker exhaustion |
| GHSA-552x-cmhc-wfg9 | Registration-code use-counter race (TOCTOU) allows over-quota account creation |
| GHSA-6r9w-whxr-3gvr | Missing authorization on cleanup-artifact endpoints (cross-engagement read & link) |
| GHSA-82jh-8f6p-vgx9 | Unbounded comment body drives multi-GB regex-findall allocation in mention parser |
| GHSA-832g-v288-v593 | Token revocation bypassable via raw-string blacklist key and fail-open lookup |
| GHSA-8357-pmf3-28f8 | Approved runbooks dereference live test-case templates at apply time |
| GHSA-88hm-p8rq-cfw2 | Automation rule conditions spoofable by naming a resource to mimic the change-summary format |
| GHSA-8r3m-6x57-pg97 | Pre-auth login/register/refresh/reset bodies parsed without `max_length` — unbounded |
| GHSA-95jh-vg44-x72r | Peer skill self-ratings and growth targets readable by any authenticated operator |
| GHSA-9cg9-3rh4-j5f5 | HTML-to-Markdown converter strips tags before decoding entities |
| GHSA-9cvp-w26m-49j9 | Template / runbook approval accepts DRAFT state, allowing a creator to swap content |
| GHSA-9h56-fv6g-5x98 | Engagement deletion erases activity-log audit trail and is permitted to read-only-admin |
| GHSA-c96m-c63f-3f2c | Presence WebSocket leaks connection slot on any non-disconnect exception |
| GHSA-cjgm-6cr5-j3x2 | Automation rule `condition.field` interpolated unescaped into a regex (ReDoS) |
| GHSA-f33c-g6w5-6xm6 | Intel-feed fetcher performs server-side requests to arbitrary URLs with redirects |
| GHSA-f826-6226-4rfw | Engagement import accepts ZIP archives with no decompressed-size limit (zip-bomb) |
| GHSA-fwvp-qc8h-r5p4 | Engagement JSON_ZIP export uses stored evidence filename verbatim as ZIP member (zip-slip) |
| GHSA-gc2q-wm5m-59xm | Registration codes generated client-side with `Math.random()` |
| GHSA-gjcp-hxgm-2vx7 | Session JWT exposed in URL query string on evidence download |
| GHSA-gv65-p25x-qrqj | Refresh token returned in JSON body and stored in `localStorage` |
| GHSA-h77m-pjqc-5cm3 | Profile-photo upload accepts arbitrary file types and `/uploads` served without auth |
| GHSA-jvcx-44v2-gc9m | Automation rules fire across all engagements, exfiltrating cross-tenant activity |
| GHSA-jw3p-gjp8-2cf3 | Infra-item delete orphans encrypted vault credentials in the database (no FK cascade) |
| GHSA-m28w-p732-3rm5 | Improper neutralization of input in notification email body |
| GHSA-m72h-rr83-jgp4 | Finding author can self-set `status=VERIFIED` with no separate-approver check |
| GHSA-pg99-33rm-7wgq | Vault and TOTP encryption keys fall back to a deterministic derivation of `JWT_SECRET` |
| GHSA-q4x9-5gmc-fxh5 | AI assistant feeds tool output back to the LLM verbatim — indirect prompt injection |
| GHSA-q8q6-22jx-7rjj | JSON_ZIP report export buffers every evidence file into a single in-memory archive |
| GHSA-rcjp-27mp-v69m | Engagement-import upload-failure fallback persists attacker-chosen storage key |
| GHSA-rrrx-36ww-rq4q | Password reset endpoints lack rate limiting and leak account existence |
| GHSA-rvcc-9pr2-v23q | Webhook `body_template` substitution unescaped — JSON injection into outbound payloads |
| GHSA-v2j8-mw59-w33v | MANAGE_GROUPS holder can grant any global permission to their own group |
| GHSA-xg53-8wgq-w9cw | Rate limiter keys on client-spoofable forwarded-IP header |
| GHSA-xqfh-2j9p-vmff | TOTP one-time codes accepted multiple times within their validity window |

## Out of scope

The following are known properties of the current design and are not treated as vulnerabilities unless the underlying threat model changes:

- **Default admin credentials (`admin` / `changeme`).** Operators are expected to change these on first login; this is documented in the README.
- **Issues that require a privileged operator role to exploit** are generally lower priority, since users with admin or team-lead roles already have broad access by design. Privilege-escalation issues that allow a lower role to gain a higher one are in scope.
