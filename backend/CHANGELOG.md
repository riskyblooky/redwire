# Changelog

All notable user-facing changes to RedWire. This file is the source for the
in-app **What's New** modal and the `/changelog` page — each `## [version] — date`
section becomes one release entry.

## [1.5.4] — 2026-08-26

### Added
- **Record a test-case result without a pass/fail verdict** — the execution flow
  gains a "No Verdict" option that marks the case executed while leaving the
  pass/fail result unset, for logging an actual result without asserting an
  outcome. Shown as "Executed / No verdict" throughout. A separate **Save**
  action logs the actual result without changing the execution status at all,
  for recording incremental work before deciding an outcome.
- **Search assets by port version** — the asset search now supports a `version:`
  token (e.g. `version:8.2`) and free-text over ports, so typing a service name
  or version string (`OpenSSH 8.2`, `Apache`) finds the asset by its port.
- **Filter by tags** on the findings and test-case tabs and the engagements
  list — a searchable, colour-coded tag multi-select in the advanced-filters
  panel (the filter icon). Engagement tag filtering is server-side so it works
  with pagination.
- **Category filter** on the findings and test-case tabs is now a searchable,
  colour-coded dropdown built from the categories actually in use (replacing the
  test-case checkbox grid; findings had no category filter before).
- **Asset filters** — the Type filter is now a searchable colour-coded dropdown
  (type badge + icon), and Created By is a searchable dropdown of the assets'
  creators with profile-photo avatars (replacing the checkbox grid and the
  free-text box). The asset search bar is also wider.
- **Filter the activity feed by specific items** — a new searchable multi-select
  on the activity feed lets you scope the stream to one or more specific
  findings, test cases, assets, or notes (in addition to the existing filter by
  resource type).
- **Activity feed filters are now searchable multi-selects** — the Type, Action,
  and User filters use a consistent searchable dropdown; Action and User (which
  were single-select) can now scope to several actions or several users at once.
  The Type filter is colour-coded per type and the User filter shows profile
  photos.
- **Activity feed date range** collapsed into a single calendar button with
  quick presets (Last 7 / 30 / 90 days, Last year) plus a custom from/to range.

### Fixed
- **Dashboard chart tooltips** no longer run off the bottom of the page for
  widgets low on the dashboard — the hover tooltip is clamped to the chart so it
  stays on-screen.
- **Test case Notes section** now starts collapsed on the view page (expand to
  read/edit), so it no longer pushes the rest of the page down by default.
- **Long titles no longer force a horizontal scrollbar** on the findings, test
  cases, and assets tab tables — the title column now truncates with an ellipsis
  (full text on hover), scaling up on wider/higher-res screens before it
  truncates.

### Added
- **Inline field editing on the test case and asset view pages** — extends the
  double-click-to-edit behaviour introduced for findings in 1.5.3 to test cases
  and assets. Test cases: title, description, execution steps, expected result,
  notes, category (searchable, colour-coded), and tags (multi-select dropdown).
  Assets: name, identifier (with a copy button), asset type (searchable, colour-
  coded), description, and notes. Each saves a single-field patch; editor-only,
  with an "add" affordance on empty optional fields.

## [1.5.3] — 2026-08-26

### Added
- **Inline field editing on the finding view page** — double-click a field to
  edit it in place and save, without opening the full edit page. Works for the
  title, the markdown fields (description, impact, steps, technical details,
  mitigations, references), severity, category (searchable, colour-coded), tags
  (multi-select dropdown), and CVSS (opens the calculator, auto-syncs severity).
  Editor-only; empty optional fields surface an "add" affordance. (Test case +
  asset pages to follow.)
- **Link attachments to a finding or test case** from the Attachments tab — a
  new "Link to…" row action opens a searchable single-target picker (with a
  "Not linked" option to clear). The backend enforces the single-target rule
  (a finding *or* a test case, not both), same-engagement scoping, and the
  chain-of-custody guard (attachments on a VERIFIED finding can't be moved).
- **Team Lead role** can now be assigned from Admin → Users (create and edit),
  alongside Operator / Read-Only Admin / Admin — the edit dialog now uses a
  single **Platform Role** dropdown.

### Improved
- **Test-case execution result** section restyled to match the app's theme (soft
  tinted Pass / Fail / No-Verdict buttons, a state-coloured result card), with
  tooltips explaining that pass/fail means the actual result matched — or didn't
  match — the expected result.
- **Attack graph now shows the test-case hierarchy** — parent → child
  (`subtest`) edges from the test-case tree are drawn (dashed, distinct from
  causal chain edges), so a hierarchical chain like "Test web app → Test auth
  → Test JWT sig → finding" reads as one connected path even when the
  intermediate parent test cases produced no findings of their own.
- **Collaborative notes editor** now shows a loading spinner ("Loading note…")
  while it connects and syncs, instead of a blank content area, and paints the
  note faster: the DB-content fallback debounce dropped from 800ms to 300ms, so
  a single user opening a note no longer waits on a fixed peer-sync window that
  will never fire.
- **ATT&CK AI auto-suggest** now works on the **test cases** sub-tab too (not
  just findings), and both sub-tabs gained an **"Include already-tagged"**
  toggle to re-suggest techniques for items that already have ATT&CK mappings.
  The suggest controls only appear when AI is configured on the instance.
- **Intel & Infrastructure linked-entities lists** now scale cleanly — because
  these are global items that can accumulate many links, the detail panels cap
  the list height with an internal scroll, add a filter box past a threshold,
  and collapse to the first few rows with a "Show all N" expander instead of
  rendering an unbounded list that overflowed the dialog.

### Fixed
- **Notification email in Outlook** — switched the email accent from the
  off-brand indigo-purple to the RedWire brand red, and render the CTA as an
  Outlook VML button so its red fill + white label survive Outlook's dark-mode
  colour transform (which previously repainted the button blue with a darkened,
  hard-to-read label). Other clients keep the CSS rounded button.
- **Cleanup actions menu** — the cleanup artifacts table now always shows the
  row actions (⋮) menu, instead of hiding it until hover, matching the
  findings / test cases / assets tables.
- **Editor hyperlinks** — typing (or a space) after a link no longer extends
  the hyperlink onto the new text, and clicking the link toolbar button while a
  link is selected now removes it (toggle off).
- **Report/download filenames with non-ASCII characters** no longer error when
  generating a report (or exporting an engagement) whose name has accented or
  non-Latin characters. Downloads now use an RFC 6266/5987 dual filename
  (ASCII fallback + UTF-8 `filename*`), so the real name renders and the header
  never fails to encode.
- **Admin users table** now shows each user's real platform role (Operator /
  Team Lead / Read-Only Admin / Admin / Read-Only) instead of labeling everyone
  who isn't an admin as "User".
- **Analytics 403 for Team Leads** — the stats/analytics scope check now honors
  a group-granted `view_all_engagements` permission (the standard 3-tier gate),
  so a user in a group with platform-wide view access can see any engagement's
  stats instead of getting a spurious 403.
- **Entity linking gaps** — the link-items action now offers every supported
  relationship consistently: the **Findings tab** can link **test cases**; the
  **Assets tab** can link **findings** and **test cases**; the finding detail
  view now actually links **assets** (the tab showed but did nothing); and the
  asset detail page now actually links **vault items** (same silent no-op).

## [1.5.2] — 2026-08-25

### Improved
- **Test-case Notes** — a test case's notes now render in a dedicated collapsible
  **Notes** section (above Evidence) through the Markdown viewer, instead of as
  plain text tucked in the sidebar.
- **Collapsible sections** on the finding and test-case view pages — every
  main content section (Executive Summary / Technical Analysis / Mitigation /
  References on findings; Description / Steps / Expected Result / Notes on test
  cases) now has a collapse toggle, and the **Evidence** section starts
  collapsed.

### Fixed
- **Cleanup tab badge** now shows the **total** number of cleanup artifacts,
  matching the other engagement tab badges, instead of only the count still
  pending.
- **ATT&CK AI suggestion** now honors the admin **AI TLS-verify** toggle, so
  technique auto-suggest works against a self-hosted AI endpoint with a
  self-signed certificate (it previously always verified).
- **Test-case category dropdown** now populates from the admin-configured
  dynamic test-case types (like findings/assets do) instead of a hardcoded
  list, on both the new- and edit-test-case pages.
- **Tags are now scoped per entity type** — a tag belongs to findings, test
  cases, OR engagements, so the Tags page tabs (and each picker) only show the
  relevant tags instead of one shared pool leaking across all tabs. Existing
  tags are kept and assigned to the type they were used with most.
- **Notes editor styling** — the collaborative notes editor (engagement Notes
  tab) now shares the standard editor's rendering styles, fixing **code blocks**
  (syntax highlighting / dark code theme) and **task-list checkboxes** (the
  themed indigo checkboxes) that had drifted out of sync and rendered unstyled.
- **PDF report generation** no longer crashes when a finding field contains a
  large markdown block (e.g. a code block taller than a page). Finding content
  now flows and paginates across pages instead of being forced onto one page,
  and long fields are no longer silently truncated.

## [1.5.1] — 2026-08-23

### Fixed
- **Notes** — the "Updated" timestamp on the notes tab no longer always reads
  "just now"; the time is now parsed as UTC (viewing a note never changes it).
- **Notification emails** — the call-to-action button now renders correctly in
  **Outlook** (padding/background moved onto the button cell), and the dark
  template now **stays dark** in dark-mode clients instead of being auto-inverted
  into an unreadable light-on-light state (declares `color-scheme: dark` and
  locks its surfaces with `bgcolor`; Apple Mail / iOS / Outlook honour this —
  Gmail still applies minor shifts but stays readable). The admin **Send test
  email** now uses this same template so you can preview it in your own client.
- **Activity feed — note edits** now show a **field-level diff** (what changed
  in the title/content) instead of dumping the entire note on every update,
  matching how finding and test-case edits already render. New notes still show
  their full content.

### Added
- **Template usage analytics** — finding and test-case templates now track how
  many times they've been applied. Each apply from the "Select a template"
  picker increments a usage counter; the picker and the Template Library both
  show the count and can **sort by most used** (a "Popular" toggle in the
  picker, a sortable **Used** column on the Templates page) — so you can see
  which templates actually get used.
- **Runbook usage analytics** — runbooks now track how many times they've been
  **applied to an engagement**, shown as a sortable **Used** column on the
  Templates page. Applying a runbook also counts a use for each test-case
  template it materializes, so template popularity reflects runbook applies too.

## [1.5.0] — 2026-08-20

### Improved
- **Notification emails redesigned** — per-user notification and automation
  emails now use a professional, branded template: the RedWire logo (embedded
  inline so it renders in every client), the dark theme with the indigo accent,
  a category badge, a details table, and a clear call-to-action button.
- **Friendly names everywhere** — the UI now shows a user's full name (falling
  back to their username) instead of the raw username, with the `@username`
  shown on hover. Applied across creator labels (findings, test cases, assets,
  cleanup, evidence, scan imports), the activity feed & logs, comments,
  notifications, and user pickers; avatar initials now use the full name too.
- **Planning inspector** — the selected engagement's team is now grouped by
  **engagement role** (Leads first, then other roles, unassigned last) instead
  of one flat list.
- **Command palette discoverability** — the global search dropped the misleading
  "Ctrl+K" hint (that shortcut opens the command palette, not the search). A VS
  Code-style **">" button** to the right of the search now opens the palette;
  Ctrl/⌘ K still opens it too.
- **Apply-template picker** — the "Select a template" modal now searches and
  pages the **whole** library on the server (debounced live search), replaces
  the crowded category chips with a funnel filter icon that reveals a
  **multi-select searchable category filter**, colors each result's category
  badge by its type (click a badge to toggle that category), and is wider.
- **Template editing** — the finding- and test-case-template edit pages now use
  the sticky bottom **"Unsaved changes"** save bar (Discard / Save) that appears
  only when there are edits, matching the finding editor, plus a navigation
  guard that warns before you leave with unsaved changes.
- **Engagements search** is now debounced (300ms), firing one request after you
  pause instead of one per keystroke — matching the Template Library search.
- **Template Library** — finding, test-case, and runbook lists are now
  **server-paged** with page controls, and search / status / category /
  "mine only" filters query the **full** library on the server (live search)
  rather than only the first 100 rows the page had loaded.
- **Client picker** — assigning an engagement's client now uses a **searchable
  list of existing clients** everywhere: the engagement overview Client card
  (available even when no client is set yet — previously the card and its edit
  button were hidden), and the new-/edit-engagement forms (replacing the plain
  dropdown).
- **Notifications popup** — hover a notification (bell icon) to read its full
  title and message in a tooltip, instead of the truncated preview.

### Fixed
- **Infrastructure** — infrastructure items can now be **edited** from the
  Infrastructure page (an Edit button on each card opens the create/edit dialog
  pre-filled). The update API existed but had no UI.
- **Template preview** — the finding/test-case preview modal now shows all
  content fields: findings gained the missing **References** and **Attack
  Techniques** sections, test cases gained **Attack Techniques**. All text
  fields render through the Markdown viewer.
- **Automations** — a "finding status changed" rule (e.g. "when a critical
  finding is marked Verified") no longer fires when a finding is first
  **created**, or when a finding is edited without changing its status. The
  status-change triggers now fire only on a real status transition. (This also
  enables the engagement/cleanup status-change triggers, which previously never
  fired.)
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
