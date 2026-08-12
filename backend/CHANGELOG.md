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
  field; they render as live diagrams (edit inline in a popover, rendered
  everywhere they're viewed).
- **Full notifications page** — reachable from the bell dropdown ("See all
  notifications"): search, status/type filters, sort, paging, and per-item
  controls (mark read/unread, delete) plus mark-all-read / clear-all.
- **Email notifications** — opt-in per-user email toggles in Profile →
  Notifications; notifications arrive as a styled HTML card instead of raw JSON,
  and a security email is sent when your password is changed.
- **Scan history** — importing an Nmap scan now captures the exact command line
  and scan metadata (scanner, timing, host counts) and keeps a revisitable
  **Scan history** per engagement.
- **Command palette + keyboard shortcuts** — Cmd/Ctrl+K to jump anywhere, plus
  two-key sequences for create/navigate actions.
- **Personal automations** — user-scoped automation rules ("My Rules") alongside
  org rules.
- **Calendar views** — Day / Week / Month / **Gantt** toggle, including a
  personal rolling Gantt timeline.
- **Version history + restore** — findings and test cases track versions and can
  be restored to a prior version.
- **Attack-graph chain links** — link findings/test cases/vault items into
  cause→effect chains.
- **HTML report format** — a self-contained interactive HTML report alongside
  PDF and JSON.
- **Engagement Specs** — phases and dates surfaced on the engagement overview.
- **In-app changelog** — this page, plus a one-time "What's New" popup after an
  update.
- **Per-feed TLS toggle** — intel feeds can individually skip TLS verification
  for internal / self-signed sources (shown with an "Insecure" badge).
- **EXIF viewer** for image evidence, and **click-to-copy** on the
  infrastructure page.

### Improved
- **Global search** now covers comments and notes.
- **Query-builder filters** use searchable entity pickers instead of raw IDs.
- **@mentions** show hover cards (avatar + name), and mention notifications jump
  straight to the comment.
- **Discussions** — edit comments in a thread; deep-link to a specific comment.
- **Scheduling** — assign selected people to an engagement with a role; OoO
  exclusion uses actual time-overlap; searchable engagement picker.
- **Engagements** — a "My Engagements" filter for all-access users, edit client
  info from the overview, and duplicate engagement names are blocked.
- **Reports** — JSON export includes linked-finding relationships.
- Timestamps are localized consistently across the app.

### Fixed
- Engagement tab counts show true totals (Assets no longer capped at the page
  size; Test Cases and Findings tabs load the full list).
- Note editor toolbar stays pinned while scrolling long notes; list markers
  render in the notes editor; note edits are logged again (debounced).
- Faster engagements list for admins (dropped redundant per-row permission
  fetches).
- Corrected several broken activity-log links.

## [1.0.0] — 2026-06-01

- Initial RedWire platform: engagements, findings (CVSS-scored), assets,
  evidence, credential vault, cleanup artifacts, runbooks, reporting, scheduling,
  discussions, and team collaboration.
