# Changelog

All notable user-facing changes to RedWire. This file is the source for the
in-app **What's New** modal and the `/changelog` page — each `## [version] — date`
section becomes one release entry.

## [1.3.0] — 2026-08-12

A large feature release.

### Added
- **Custom fields** — admin-defined fields on assets, test cases, findings,
  clients, and engagements; usable as sortable table columns, searchable, in
  generated reports, and in the query builder.
- **Dashboards & widgets** — a much bigger query builder (20+ tables, richer
  operators, multi-source), a multi-query wizard for composite widget types,
  per-user activity series, and **tabbed global stats pages** with shared layouts.
- **Plugin system** — drop-in plugins with backend routers, frontend pages and
  in-page **extension slots** baked into the app, per-plugin migrations,
  lifecycle events, and RBAC.
- **Activity Feed** — the engagement *Logs* tab is now **Activity**, with a new
  **Feed**: a chronological, single-pane-of-glass stream of everything operators
  posted (comments, notes, findings, test cases, assets, evidence), with
  field-level **diffs** for finding/test-case edits. Search, type/action/author/
  date filters, sort, and paging.
- **Mermaid diagrams** — author ` ```mermaid ` blocks in any editor or markdown
  field; they render as live diagrams.
- **Notifications** — a full **/notifications** page (search, filters, sort,
  paging, per-item read/unread/delete), opt-in **per-user email notifications**
  as a styled HTML card, and a **password-changed security email**.
- **Scan history** — Nmap imports capture the exact command line and scan
  metadata (scanner, timing, host counts), kept as a revisitable per-engagement
  history.
- **Command palette + keyboard shortcuts** — Cmd/Ctrl+K, plus vim-style hotkey
  sequences.
- **Personal automations** — user-scoped automation rules alongside org rules.
- **Calendar views** — Day / Week / Month / **Gantt** toggle.
- **Attack-graph causal chains** — link test cases, findings, and vault items
  into cause→effect chains.
- **Version history + restore** for findings and test cases.
- **Tags on engagements**; **clipboard-paste uploads** + one shared dropzone
  across attachment surfaces; uploads persist across rebuilds.
- **AI & LDAP tooling** — custom headers / TLS-verify toggle / larger key field
  for AI providers; LDAP test-login + connection debug tracing.
- **In-app changelog** — a `/changelog` page and a one-time **"What's New"**
  popup after each update.
- **Per-feed TLS toggle** for internal / self-signed intel feeds.
- Engagement **Specs** (phases + dates), edit client info from the overview, a
  **"My Engagements"** filter, imports pre-scoped to an engagement, and `/health`
  build metadata surfaced in an admin **About** tab.

### Improved
- Global search now covers notes and comments.
- Query-builder filters use searchable entity pickers instead of raw IDs.
- @mentions show hover cards; mention notifications deep-link to the comment;
  comments are editable in threads.
- Scheduling: assign people to an engagement with a role; OoO exclusion uses a
  configurable time-overlap threshold.
- Clients: search + filter chips, sub-client actions, searchable parent picker.
- JSON report export includes entity relationships.
- Timestamps are localized consistently across the app.

### Fixed
- Engagement tab counts show true totals (Assets no longer capped; Test Cases &
  Findings load the full list).
- Notes editor toolbar stays pinned while scrolling; list markers render;
  debounced note-edit logging restored.
- Faster engagements list for admins (fewer redundant permission fetches).
- Calendar weekend default + self Out-of-Office creation; widget tooltip
  clipping/theming; client tree badge rollup; several broken activity-log links.
- Pinned the MCP SDK so fresh builds don't pull a breaking 2.0 API.

## [1.2.0] — 2026-06-11

### Security
- Coordinated-disclosure hardening release: vault field encryption at rest and
  on import; auth/session hardening (HttpOnly refresh cookie, one-time TOTP,
  token-revocation fixes, rate-limited password reset with off-request email);
  plugin route authentication + runtime disable gate; automation template
  escaping and field constraints; input size caps (uploads, imports,
  comments/notes); server-side CSPRNG registration codes; profile-photo and
  `/uploads` lockdown; and more.

### Added
- **Report classification & portion marking** plus deep report customization.

## [1.1.0] — 2026-05-20

### Security
- Coordinated-disclosure security release (credited to the Lockheed Martin Red
  Team) — hardening across authentication, uploads, and API input validation.

## [1.0.0] — 2026-05-11

- Initial public release of the RedWire red-team operations platform:
  engagements, findings (CVSS-scored), assets, evidence, credential vault,
  cleanup artifacts, runbooks, reporting, scheduling, discussions, and team
  collaboration.
