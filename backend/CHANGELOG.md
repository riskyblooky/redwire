# Changelog

All notable user-facing changes to RedWire. This file is the source for the
in-app **What's New** modal and the `/changelog` page — each `## [version] — date`
section becomes one release entry.

## [1.5.0] — Unreleased

### Improved
- **Notifications popup** — hover a notification (bell icon) to read its full
  title and message in a tooltip, instead of the truncated preview.

### Fixed
- **Notifications popup** — relative timestamps no longer always render "just
  now"; the created-at time is now parsed as UTC.
- **What's New modal** no longer reopens on every page navigation. It now only
  surfaces released entries (newer than last-seen, up to the running version), so
  a version skew between the changelog file and the running build can't leave an
  entry permanently un-dismissable.

## [1.4.0] — 2026-08-19

### License
- **RedWire is now licensed under Apache 2.0** (previously SSPL v1), and ships a
  NOTICE file. RedWire may now be used, modified, and redistributed — including
  in closed-source and commercial deployments — under Apache-2.0's permissive
  terms.

### Added
- **In-app help** — a `/help` guide hub with **User**, **Admin**, and **Plugins**
  guides (deep-linkable sections, live Mermaid diagrams, real in-app icons), plus
  a page-aware **?** button in the header that explains the current page and links
  into the relevant guide.
- **What's New** — the changelog is now reachable from the user menu.
- **Calendar timeline** — the planning timeline gains a **Calendar / Gantt toggle**
  and a custom **date-range filter**, with month navigation and per-day
  engagement chips.

### Improved
- **Custom-field editing** — text fields now edit with the rich Markdown editor
  and render as Markdown; findings and test-case edit pages moved custom fields
  into their own tab; custom-field sections (and evidence EXIF) collapse by
  default on detail views.
- **Faster large lists** — the Findings and Test Cases tabs use infinite scroll
  (the first page renders immediately, more stream in as you scroll) and no
  longer fire redundant per-row requests.
- **Faster engagement pages** — detail tabs load lazily via count/link endpoints,
  and profile-photo fetches are deduped and cached.
- **MCP server** migrated to the MCP 2.0 SDK.

### Fixed
- Findings tab now shows linked **test cases** in the links column.
- The Classification Marking card no longer renders empty on the edit-test-case
  page when no marking profile applies.

## [1.3.0] — 2026-08-13

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
- **Faster engagement pages** — detail tabs load their data only when opened
  rather than all up front; tab badges and the overview read lightweight count
  endpoints, and the findings / test-case tables batch their linked-note and
  linked intel/infrastructure lookups into a single request each instead of one
  per row.
- **Consistent page-title icons** — every top-level page now uses the same
  themed title-icon treatment.
- Profile photos load once and are cached instead of being re-fetched for every
  table row that shows the same author.

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
