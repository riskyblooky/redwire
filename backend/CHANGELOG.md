# Changelog

All notable user-facing changes to RedWire. This file is the source for the
in-app **What's New** modal and the `/changelog` page — each `## [version] — date`
section becomes one release entry.

## [1.1.0] — 2026-08-12

### Added
- **Activity Feed** — the engagement Logs tab is now **Activity**, with a new
  **Feed** view: a chronological, single-pane-of-glass stream of everything
  operators posted (comments, notes, findings, test cases, assets, evidence),
  with **field-level diffs** for finding/test-case edits. Rich filters (search,
  type, action, author, date range), sort, and paging.
- **Mermaid diagrams** — author ` ```mermaid ` blocks in any editor or markdown
  field; they render as live diagrams (edit inline in a popover, view rendered
  everywhere).
- **Email notifications** — per-user email toggles in Profile → Notifications
  and the notification settings panel; notifications now arrive as a styled HTML
  card instead of raw JSON.
- **Full notifications page** — reachable from the bell dropdown ("See all
  notifications"): search, status/type filters, sort, paging, and per-item
  controls (mark read/unread, delete) plus mark-all-read / clear-all.
- **Scan history** — importing an Nmap scan now captures the exact command line
  and scan metadata (scanner, timing, host counts) and keeps a revisitable
  **Scan history** per engagement.
- **Per-feed TLS toggle** — intel feeds can individually skip TLS verification
  for internal / self-signed sources (shown with an "Insecure" badge).
- **Password-changed security email** — completing a password reset now emails
  the account owner so an unauthorized reset is noticed.

### Fixed
- Engagement tab counts show true totals (Assets no longer capped at the page
  size); Test Cases and Findings tabs load the full list.
- Note editor toolbar stays pinned while scrolling long notes; list markers
  render in the notes editor.
- Restored debounced activity logging for note edits.
- Faster engagements list for admins (dropped redundant per-row permission
  fetches).

## [1.0.0] — 2026-06-01

- Initial RedWire platform: engagements, findings (CVSS), assets, evidence,
  credential vault, cleanup artifacts, runbooks, reporting, scheduling,
  discussions, and team collaboration.
