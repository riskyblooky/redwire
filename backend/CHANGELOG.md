# Changelog

All notable user-facing changes to RedWire. This file is the source for the
in-app **What's New** modal and the `/changelog` page — each `## [version] — date`
section becomes one release entry.

## [1.9.0] — Unreleased

### Added
- **Security Center** (Admin → Security) — one place to watch the
  instance's own security. Sign-ins: every successful and failed sign-in
  (with the reason), failed 2FA codes, sign-outs, password and 2FA changes,
  API-token changes, rate-limit hits and SSO errors, with IP and browser,
  plus top failing IPs and most-targeted usernames. Web traffic: every
  request nginx served — the web app as well as the API — with status mix,
  top client IPs, scanner probes (`/wp-login.php`, `/.env`, `/.git/…`),
  scanner and tool user agents, and a searchable request log. Accounts &
  tokens: who lacks 2FA, dormant accounts, risky API tokens, with sign-out-
  everywhere, disable and revoke actions. Posture: a configuration
  checklist (keys, admin 2FA, default passwords, LDAP/SMTP TLS, CORS, TLS
  certificate expiry, …) with fixes. Admin audit: every admin
  configuration change and sensitive action such as vault secret reveals.
  New `view_security_center` / `manage_security_center` permissions
  (read-only admins can view). Retention is configurable (raw web requests
  14 days by default).
- **Upgrading:** redeploy with the new `docker-compose.yml` and
  `nginx/nginx.conf` — nginx now also writes a JSON access log to a new
  `nginx_logs` volume shared with the backend.

### Security
- **Delegated user managers can no longer escalate.** Anyone holding
  `manage_users` without being an admin (Team Leads have it by default)
  could make themselves or anyone else an admin, add themselves to any
  group, or reset an admin's password and sign in as them. They can now
  only assign Operator, Read-Only or their own role, only act on accounts
  that hold no permissions they lack, and only add users to groups whose
  permissions they already have. The duplicate `PUT/DELETE /users/{id}`
  and `POST /users` routes, which skipped these checks, are removed; use
  `/admin/users`.
- **View-only users can no longer change live-edited text.** On the
  live-editing connection for notes and record fields, a user with view
  access only could send a crafted sync message that an editor's browser
  merged and then auto-saved. Those messages are now dropped for
  view-only users.
- **Cleanup artifacts can only be linked within their own engagement.**
  Linking one to a finding, test case or asset from a different
  engagement was accepted and then showed that record's name and
  identifier on the artifact. It now returns 400, like the other link
  endpoints.
- **Restoring a finding version follows the same rules as editing it.**
  It needed only basic edit permission, so a member could rewrite a
  colleague's finding without `finding_edit_any`, or an author could
  restore their own finding to an earlier VERIFIED or CLOSED snapshot and
  skip the separate-reviewer and peer-review rules. Both now apply.
- **Infrastructure vault secrets are no longer sent in the item list.**
  Listing an infrastructure item's vault returned every decrypted
  password and note at once, with no record of who looked. The list now
  shows only whether a secret is set; the value comes from a separate
  reveal request (used by the Show, Copy and Edit buttons), and each
  reveal or file download is recorded in the Security Center.
- **Lists, search and the activity feed respect per-resource view
  permissions.** Engagement roles can withhold e.g. `finding_view` or
  `note_view`, and opening a single finding or note honoured that, but the
  findings, test cases, assets and threads lists, global search, the
  engagement activity feed (which includes note text, finding descriptions
  and comments), the engagement evidence list, and the AI assistant's
  `search` and `get_field_examples` tools only checked membership. They
  now apply the same view permission as the single-item page. The built-in
  roles hold all view permissions, so they see no change.
- **Intel items only show linked records you can see.** An intel item's
  detail listed every linked finding, test case and note by title across
  all engagements, and anyone with `intel_edit` could unlink them. Both
  now require view access to the linked record's engagement.
- **Password changes end API tokens, and reset and 2FA links are single
  use.** Changing or resetting a password (yourself, forced, by an admin,
  or by email link) now deactivates the account's API tokens as well as
  its sessions, as email and 2FA changes already did. A used
  password-reset link, and the short-lived token between password and 2FA
  code at sign-in, can no longer be replayed.
- **Attack-graph edges can only be changed within your own engagement.**
  Edit access on one engagement's attack graph was enough to add or
  delete attacker edges on another engagement's graph, given its attacker
  node id.
- **The backend refuses to start with a weak `JWT_SECRET`.** It used to
  fall back to the default published in the repo with only a log warning,
  so anyone could sign their own admin token. It now stops at startup if
  `JWT_SECRET` is unset, the default, or shorter than 32 characters. The
  production compose file also requires `POSTGRES_PASSWORD`,
  `REDIS_PASSWORD`, `MINIO_ROOT_PASSWORD`, `JWT_SECRET` and
  `ADMIN_PASSWORD` to be set instead of defaulting to `changeme` /
  `minioadmin`. `deploy_server.sh` already generates all of them.
- **Plugin settings are encrypted at rest.** Plugin secrets such as the
  ServiceNow password and the Shodan API key were masked in the admin UI
  but stored unencrypted in the database. Every plugin setting value is
  now encrypted with the vault key, and existing values are encrypted
  automatically on the first start after upgrading. The Security Center's
  posture check reports any that couldn't be.

### Fixed
- After a forced password change, the new session was sometimes signed
  out on its next request. The sign-out-everywhere cutoff and token issue
  times are now compared in whole seconds.
- **A sign-in completed with a 2FA code now fires the `auth.login.success`
  plugin event** — previously only password-only sign-ins did.
- **Plugin events for creates, updates and deletes now fire** — plugins
  subscribed to the documented `<resource>.created` / `.updated` /
  `.deleted` events (e.g. `asset.created`) never received them; they were
  sent under the internal activity names (`asset.created_asset`). Login,
  status-change and report events were unaffected.
- **Sample plugins work** — the Shodan and ServiceNow samples now react to
  new assets, use the asset's identifier (IP / hostname) rather than its
  display name, and their routes work for anyone who can view the asset
  instead of admins only. Shodan's manual enrich no longer errors.
  ServiceNow keeps TLS verification on and can't have its search widened by
  query syntax in the search text. Plugin authors get a startup warning if
  a plugin requires an engagement-level permission for all its routes.

## [1.8.1] — 2026-11-08

### Security
- **Read-only admins can no longer make changes** in a few places that
  still let them: saving or creating report layouts, importing scans,
  linking and unlinking findings / test cases / assets / notes / vault
  items / cleanup artifacts, editing cleanup-artifact links, and managing
  infrastructure vault items. The role can still view all of these, and
  can still edit where an engagement role explicitly grants it.

## [1.8.0] — 2026-11-07

### Added
- **Edit together, live** — the text fields on the finding, test case and
  asset edit pages, and text sections in the report builder, now update for
  everyone on the page as they type, with each person's cursor shown by name.
  Review-comment highlights stay in place while others edit. Fields open
  instantly with their saved text while the live connection starts.
- **Text fields save themselves** — those live fields save a moment after
  you stop typing (and when you leave the page), shown as *Saving…* /
  *Saved* above the field, so text edits alone no longer need Save. Each
  editing session adds one entry to the record's version history and
  activity feed, not one per save. Severity, status and other fields still
  need Save, which keeps review checks, notifications and automations tied
  to it; the "also editing" banner says those are saved by whoever saves
  last. Restoring an old version is refused while someone else has the
  record open for live editing, since their editor would save the old text
  back.
- **Asset version history** — assets now keep versions like findings and
  test cases: see what changed (name, type, identifier, description,
  notes, pwned, in scope) and restore an earlier version from the asset
  page or its edit page. Asset updates in the activity feed show the change.
- **Who's editing an asset** — the asset edit page shows who else is viewing
  or editing it, like findings and test cases.

### Changed
- **Who's here avatars** — your own avatar is always the rightmost; others
  stack to its left, newest furthest left and on top.

### Fixed
- **Blank asset Type on edit** — assets saved with older type spellings
  (`IP_ADDRESS`, `host`, `web_application`…) showed an empty Type dropdown
  when edited. Existing assets are converted to the matching configured type
  (unknown ones become *Other*), and new or edited assets, imports,
  engagement transfers and spray-created hosts always use a configured type.
  The API now rejects a type that matches none, listing the valid ones.

## [1.7.1] — 2026-11-05

### Security
- **Live activity feed identity** — a browser could change the user identity
  on its live-update connection after signing in, and the dashboard's live
  activity feed then delivered events meant for the user it claimed to be.
  Since 1.7.0 gave admins the feed for every engagement, claiming an admin's
  identity exposed activity across all engagements. The connection now keeps
  the signed-in identity; the browser can only say whether it is viewing or
  editing. Upgrade from 1.7.0 promptly.

### Fixed
- **Who's here avatars** — people viewing or editing a page show their name
  and photo again instead of "??", and the "also editing" warning on edit
  pages appears again (both broke with 1.7.0's multi-worker presence).

## [1.7.0] — 2026-11-05

### Added
- **Live updates work across backend workers** — WebSocket events (activity
  feed, notes, discussions, presence avatars, cursors and live note editing)
  now go through Redis, so they reach every user even when the backend runs
  more than one worker or replica. Single-worker installs behave as before,
  and if Redis is unreachable the backend falls back to single-process
  delivery. Set `WS_FANOUT=false` to turn it off.
- **Ready for multiple backend workers** — login and other rate limits are
  now counted in Redis, so adding workers doesn't multiply them. The
  background intel feed refresh runs on one worker at a time. The password
  wordlist filter is kept as one shared copy in Redis, built once instead of
  by every worker. Wordlist imports and deletions apply everywhere
  immediately, and backend restarts no longer rebuild the filter from the
  database.

- **Paste images into templates and intel** — finding, test-case and
  report-layout templates and intel items now accept pasted or dropped
  images. They're stored as shared library images that anyone signed in can
  view, the same people who can see the templates, and they carry into
  findings and reports created from those templates. The new-engagement form
  explains that images can be added once the engagement exists, instead of
  showing an error.
- **"Model not allowed" on the findings list** — findings scored with a model
  their engagement no longer allows are flagged in the engagement's findings
  table and on the Findings page, as they already were on the finding itself.

### Fixed
- **Pasting images into discussion comments** — images pasted or dropped into
  a comment reply now upload instead of failing.
- **Live activity feed for admins** — admins, read-only admins, team leads and
  anyone with *view all engagements* now get live dashboard updates for every
  engagement they can view, not only the ones they're assigned to.

### Changed
- **The backend runs two workers by default** — the production compose file
  now starts two backend worker processes, so one slow request no longer
  holds up everyone else. Set `BACKEND_WORKERS` in `.env` to change the
  number; each worker uses about 200 MB. Enabling or disabling a plugin now
  takes effect on every worker, and startup setup runs one worker at a time.

## [1.6.2] — 2026-11-04

### Fixed
- **Report sections keep their identity on save** — saving a report layout
  used to delete and recreate every section. Sections are now updated in
  place, so their review threads stay attached; removing a section deletes
  its threads. Engagement import keeps report-section threads attached too.
- **Threads left behind by deleted items** — deleting a finding, test case,
  asset, cleanup artifact, evidence file, note or vault item now deletes its
  discussion threads too. They used to stay in the engagement's discussions
  list, linking to nothing.
- **Highlight comments survive engagement export/import** — exported threads
  now include their highlight position, so after an import they still show as
  highlighted comments instead of plain threads.
- **Pasting images into report sections** — pasting or dropping an image into
  a report builder text section failed with "Image upload requires an
  engagement context". The same fix applies to the engagement, asset and test
  case description editors.
- **Scoring policy on the engagement page** — the engagement's allowed and
  default scoring models now offer only the models enabled site-wide, and the
  section is read-only while the site allows a single model. Saving a model
  the site doesn't enable is rejected.
- **Editing findings scored under a dropped model** — a finding scored with a
  model its engagement no longer allows could not be saved at all (any edit
  returned a "not permitted" error). It now saves and keeps its score until it
  is rescored.

### Security
- **Engagement status rules** — non-admins can now move an engagement forward
  any number of stages or back one, put it on hold from any open stage and
  resume to any open stage; Completed is reachable only from Reporting.
  Admins and team leads can still make any change. The edit page greys out
  statuses you can't move to.
- **Approved runbooks are frozen** — approving a runbook snapshots its
  test-case templates, and applying a published runbook uses that snapshot,
  so editing or unpublishing a template later can't change what an approved
  runbook creates. Runbooks already published are frozen at their current
  content on upgrade; editing a published runbook's items refreezes them.
- **New default permissions reach existing installs** — permissions a release
  adds to the default groups and roles are now granted once to existing
  deployments (tracked by a seed revision), instead of reaching only fresh
  installs. A grant an admin later removes stays removed. This release grants
  Team Leads *manage marking profiles*, Engagement Lead *evidence edit* /
  *evidence edit any*, and Operator *evidence edit*.
- **Deleted-engagement audit logs** — a new Admin → Audit tab lists deleted
  engagements with their surviving activity history (who did what, when),
  previously reachable only from the database. Visible to admins, read-only
  admins and anyone with *view all engagements*. Engagements deleted before
  this release show only their deletion record.

### Added
- **httpx and NetExec (nxc) scanner imports** — the scanner import now accepts
  httpx JSON/JSONL output (hosts, web ports, server, page titles and
  technologies) and NetExec console or `--log` output (hosts and services
  from nxc's host banners). NetExec flags become findings: SMB signing not
  required, SMBv1 enabled, SMB null sessions and RDP without NLA. Credential
  results are left to the Spray import, and passwords in a logged command line
  are masked.
- **Classification banner on engagements** — engagements with a marking
  profile show a banner across the top of the engagement page with their
  default level in its colors, plus the profile and ceiling.
- **Review threads on report sections** — report builder sections now support
  the same peer-review comments as findings. In a saved text section, select
  text to leave a highlighted comment. Every section also has a "Review
  threads" list, collapsed by default, for general discussion; the
  all-sections view shows each section's open-thread count. Mention
  notifications link straight to the section.
- **Marking column on the engagements list** — shows each engagement's
  marking profile; hover it to see the profile's levels.
- **"Model not allowed" indicator** — findings scored with a model their
  engagement no longer allows show a warning on the finding page, the finding
  side panel and the edit page, which explains how to rescore with an allowed
  model.

## [1.6.1] — 2026-10-29

### Security
- **Interactive HTML report: stored XSS** — finding titles, asset names, CVSS
  vectors, cleanup-artifact fields and attack-graph labels were inserted into
  the interactive HTML report without escaping, so markup in any of them (typed
  by a user or carried in from imported scanner output) ran as script when the
  report was opened. Every such field is now escaped. Affects HTML reports
  generated since the interactive report was introduced; regenerate any HTML
  reports you have shared.
- **Request size caps** — the scoring-policy settings, attack-chain link and
  AI-chat mode fields now enforce maximum lengths like every other request
  field.

### Changed
- **Severity colors** — the remediation tracker, report-builder pickers and
  threat-intel severities now use the shared severity palette too.

### Fixed
- **Burp and Nessus imports** — on public installs the Burp and Nessus parsers
  failed to load, so uploading either scan format errored; a finding whose
  creator had been deleted could also fail to display. Both fixes were in the
  development tree but had not reached the public release.

## [1.6.0] — 2026-10-29

### Added
- **Pluggable finding scoring** — findings can be scored with rating models
  beyond CVSS 3.1. A **Scoring Model** picker on the new and edit finding pages —
  and inside the double-click score editor on the finding view page and the side
  sheet — lets you choose a model; the calculator renders that model's metrics
  (selects and 0–N button scales) and computes the score and severity live.
  Built-in models:
  - **CVSS 3.1** — the existing base-score calculator.
  - **DREAD** — mean of the five 0–10 factors.
  - **OWASP Risk Rating** — Likelihood × Impact from their factor groups, via the
    OWASP severity matrix.
  - **USAF Risk Assessment Matrix** — MIL-STD-882 hazard Severity (I–IV) ×
    Probability (A–E) → Extremely High / High / Medium / Low.
  Every model maps onto the existing Critical/High/Medium/Low/Info scale, so
  dashboards, reports, analytics and automation are unaffected. The rating is
  recomputed on the server when a finding is saved, so it is always authoritative,
  and each finding remembers which model and inputs produced it.
- **CVSS 4.0 scoring (plugin)** — a bundled **CVSS 4.0 Scoring** plugin adds
  CVSS 4.0 (CVSS-B) as a scoring model. It appears in the Scoring Model picker
  like the built-ins; its engine is a faithful port of FIRST.org's reference
  calculator (validated to match exactly across 25,000 vectors). Plugins can now
  contribute scoring models — a declarative model definition plus, for complex
  math, a scoring engine — through the plugin system.
- **Scoring-model policy** — admins choose which scoring models are enabled
  site-wide, the default model, and optionally lock every finding to a single
  model (**Admin → Policies → Scoring models**). Each engagement can narrow that
  further with its own allowed models and default (**Edit engagement → Scoring
  policy**). The model pickers only offer permitted models and lock when just one
  is allowed, and the server rejects a finding scored with a disallowed model.
- **Admin Policies tab** — site-wide policy settings (stats scope, peer review,
  scoring models) now live together on a new **Policies** tab in the admin area.
- **Model-aware score display** — reports (PDF, HTML, Markdown) and the finding
  view, side sheet and remediation tracker label each finding's score with the
  model that produced it instead of a fixed "CVSS 3.1". Categorical models show
  their outcome (e.g. USAF "Extremely High") rather than a number, the HTML
  report's metadata lists the scoring models used, and JSON exports include
  each finding's `score_model` and `score_inputs`.
- **MCP: scoring models** — `create_finding` and `update_finding` accept
  `score_model` + `score_inputs` (the server computes the rating), and new
  `list_scoring_models` / `get_scoring_model` tools let MCP clients discover the
  models an engagement permits and their metrics.

### Fixed
- **MCP `create_finding` always failed** — the tool sent `engagement_id` only
  as a query parameter, but the API requires it in the body, so every call was
  rejected; its schema also omitted the required `description`. Both fixed.
- **Let's Encrypt renewals not taking effect** — the certbot container renewed
  certificates on schedule, but nginx kept serving the old certificate from
  memory until it was restarted, so the site's certificate expired despite a
  valid renewal on disk. The production nginx container now reloads every 6
  hours to pick up renewed certificates.

### Changed
- **Consistent severity colors** — severity badges, accents and charts across
  findings, test cases, assets, imports, the attack graph, analytics and client
  stats now share one palette (Critical red, High orange, Medium yellow, Low
  light blue, Info slate). Previously some views showed Medium as amber and Low
  as a darker blue.
- **New finding page: Custom Fields tab** — custom fields moved from the sidebar
  into a **Custom Fields** tab in the main editor, matching the edit page. The
  tab only appears when finding custom fields are defined.

## [1.5.7] — 2026-09-21

### Added
- **Anchored peer-review comments** — highlight a span of text inside a finding or
  test-case field and attach a review thread to it, Google-Docs style. Double-click
  a field (or its comment-count chip) to open annotation mode: an editor with the
  review highlights beside a comments panel. Select text → **Add comment** anchors a
  thread to that span; highlights track edits live and re-anchor on save, and a
  comment whose text is later deleted is flagged **Outdated** rather than lost.
  Works on every text field of findings and test cases, on the detail pages, the
  side sheets, and the full edit pages. Reviewers who can view a finding can comment
  even without edit rights. Available across the app since it's built into the
  shared editor.
- **Peer review ties into comments** — leaving an anchored comment on a finding
  automatically records your peer review as *changes requested* (the author is
  skipped). Anchored review threads are titled `<Field> Review #N`.
- **Attack graph on finding & test-case pages** — a collapsible **Attack Graph**
  section on the finding and test-case view pages shows that item's attack path:
  the chain that led to it (upstream) and what it produced downstream, with the
  same interactive controls as the reporting page (drag to connect, edit/delete
  edges) so chains can be built and edited right from the view page.
- **Tags column on the findings & test-case tabs** — an optional **Tags** column
  (hidden by default; enable it from the column toggle) shows each row's tags.

### Improved
- **Reports draw the attack path from your authored chains** — the PDF and
  interactive HTML reports now build each finding's attack path from the causal
  chains you author in the app (falling back to the test-case→finding→asset
  associations when a finding has no chain), so what you edit in the attack graph
  is what the report shows. The reporting page's attack-graph selector now picks a
  **finding** to view its chain (instead of an auto-detected cluster).
- **Result counts by the search bar** — the finding, test-case, asset, attachment,
  vault, cleanup and notes tabs (and the clients, tags, template and test-case
  list pages) now show a live "N results" count next to the search box, in a
  fixed slot so the controls don't shift as you type.
- **Clickable attachments in tab tables** — linked evidence in the Links column of
  the finding/test-case tables now opens the attachment view page, like linked
  findings and test cases already did.

### Improved
- **Annotation editor UX** — the comments panel is resizable (drag its edge) and
  collapsible; the editor keeps its own vertical resize grip; the "Add comment"
  button and composer now sit over the editor near your selection instead of
  drifting off-screen. Comments render Markdown, show the author's avatar (hover for
  the name), and a header toggle hides resolved threads (resolved threads also drop
  their highlight). Thread/comment delete controls were added to the panel.
- **Cleaner discussion section** — the resource's discussion area is now titled
  **Peer-review comments**, collapses from its title, keeps the anchored ("highlight")
  threads hidden behind a toggle to stay focused on general discussion, and shows the
  anchored field + quote for context. Thread/comment counts moved onto the title row.
- **Two-row editor toolbar** — the formatting toolbar no longer wraps: everyday
  controls stay on the primary row and the lesser-used ones (underline, highlight,
  colour, sub/superscript, alignment, task list, blockquote, Mermaid, table) move
  behind a **More** toggle (remembered per user). Applies everywhere the editor is used.
- **Collapsible right pane** on the finding and test-case detail pages — collapse the
  Risk Assessment / Test Details sidebar to give the main content full width (a slim
  "Details" tab brings it back; remembered per view). The Execution Result section on
  the test-case page is now collapsible too.
- **Tighter, more consistent detail pages** — reduced the heavy section padding and
  normalized section-title sizing on the finding/test-case view pages, and gave the
  finding's Executive Summary the same boxed style as Technical Analysis.

### Fixed
- **Edit pages: sticky tabs & sidebar** — on the finding/test-case edit pages the tab
  bar now stays pinned below the header while the sections scroll, and the right
  sidebar pins at the correct offset instead of sliding under the header.

## [1.5.6] — 2026-09-09

### Security
- **New users no longer get platform-wide engagement visibility by default** —
  `VIEW_ALL_ENGAGEMENTS` was removed from the built-in **Default** group (it
  grants view of *every* engagement's findings/assets/vault/etc. and proposed
  engagements). New users now see only the engagements they're assigned to;
  grant `VIEW_ALL_ENGAGEMENTS` via the Team Leads group or explicitly for a
  cross-engagement viewer. (Existing installs: remove it from the Default group
  in Admin → Permissions to apply.)
- **Closed several endpoints that skipped their permission check** — a permission
  audit found endpoints that returned or changed engagement data for any signed-in
  user, regardless of assignment: the finding remediation summary, per-asset
  remediation toggle, reading/resolving discussion comments, linking test cases to
  findings/assets, reading engagement phases, and the ATT&CK coverage/Navigator
  exports. They now enforce the matching finding / test-case / discussion /
  engagement permission, and the dashboard "computed metrics" are scoped to the
  caller's engagements like the rest of the stats.

### Changed
- **Permission consistency (assignable, not role-hardcoded)** — user, group,
  engagement-role, and registration-code management; finding/test-case templates,
  runbooks, report themes/layouts; and engagement creation now enforce their
  assignable permissions (grantable via a group) instead of a hardcoded admin/lead
  role. The **Team Lead** role remains a blanket bypass for *engagement* work;
  platform-wide management now comes from **group permissions** (the admin
  edit-user dialog now explains this). Read-only admins keep read access to RBAC
  config but can no longer perform these writes.
- **Removed the unused "Customize Dashboard" permission** — it was defined and
  grantable but never enforced (personal dashboard layout is available to every
  user regardless), so it's gone from the permission list.
- **More admin surfaces are now delegatable** — configurable types, marking
  profiles, and custom-field definitions gained assignable permissions
  (`manage_configurable_types`, `manage_marking_profiles`, `manage_custom_fields`)
  instead of being hardcoded admin-only; engagement **import** now uses the
  `create_engagement` permission and the **proposed-engagements** views use
  `view_all_engagements`. Wordlist hash lookup/check stays open to any operator by
  design (it's a core capability, like the password-change bloom check).
- **Admin console is permission-gated per tab** — a user with a delegated
  management permission (e.g. custom fields, taxonomy, skills, widgets) now sees
  the **Admin** link in the sidebar, can open the Admin area, and sees only the
  tabs they can manage, instead of the whole console being restricted to the
  admin roles. Within the Operators tab, the create/edit/delete controls only
  appear for users with `manage_users`. Admins/read-only admins still see
  everything.

### Added
- **Peer review for findings** — operators can now review a finding and record an
  **Approve** or **Request changes** verdict from the finding's sidebar
  (discussion stays in the finding's comment threads). A new admin policy
  (**Admin → Permissions → Finding peer
  review**) can require a configurable number of independent approvals before a
  finding may be marked **Verified**. When required, the verify action is blocked
  (for everyone, including team leads and admins) until the threshold is met; a
  finding's author can never approve their own work. The sidebar shows approval
  progress, who reviewed, and how many more approvals are needed.
- **Effort / time-on-task metrics** — the Analytics page now shows estimated
  active time per work type (findings, test cases, assets, notes), derived from real
  editing activity (the visibility+interaction-gated heartbeat now records which
  record you're working on) and bucketed into sessions. Aggregated and
  anonymised — totals and contributor counts only, never per-person.
- **Edit text attachments in-app** — text files (`.txt`, `.md`, `.log`, …) now
  have an "Edit Text" action that turns the preview area into the editor in place
  (no popup) and saves back over the attachment, alongside an inline text preview.
- **Edit CSV attachments as a table** — CSV attachments render as a
  spreadsheet-style grid (row numbers, column letters, add/delete rows &
  columns) for both preview and edit-in-place.
- **Editor line numbers + active-line highlight** — a toolbar toggle adds a
  numbered gutter to the editors (finding/test-case/note fields and the notes
  tab) and highlights the line the cursor is on.

### Improved
- **Half-view side sheets now show (and edit) almost everything the full page does** —
  the quick-look side panels for findings, test cases, and assets were missing a lot
  of detail; they've been brought close to parity with their full pages. Findings
  gained peer review (and the same gate blocking Verified until approvals are met —
  previously the sheet could bypass it), discussion + remediation threads, affected
  targets with per-asset remediation/progress/ports, evidence, steps to reproduce,
  references, and a full CVSS vector with copy. Test cases gained execution recording
  (pass/fail/actual result), their own notes field, discussion, and an evidence
  gallery. Assets gained discussion, port service versions, and clickable
  cleanup/vault links. All three now support inline quick-edit (title, status,
  severity/type, category, tags, and the markdown fields) right from the sheet, plus
  reviewer presence and live refresh — no need to open the full page for routine edits.
  Each section in these sheets is collapsible (defaults matching the full page), so
  the narrow panel stays manageable.
- **Condensed the "Linked Resources" panel** — on the finding and test-case detail
  pages and their side-sheet ("half") views, the linked items (test cases,
  findings, assets, vault items, cleanup artifacts, notes, intel, infrastructure)
  now flow in one tight list under a single header instead of a titled sub-section
  per type. Each item's colored icon identifies its type, saving a lot of vertical
  space.
- **More pages update live** — finding/test-case/asset/attachment **detail**
  pages now refresh in place when a teammate edits the record (previously they
  showed the teammate's presence but stale content), the Operations Analytics /
  stats page refreshes on tracked changes instead of only on load, and the
  Infrastructure page updates live when items change. Redundant fallback polling
  was trimmed (admin user list 15s→30s, notifications 60s→300s) now that these
  are WebSocket-driven.
- **Accurate online/active indicators** — a user's "active" status is now driven
  by real activity (a heartbeat sent only while the tab is visible and the user
  has interacted recently) instead of any authenticated request. An idle tab left
  open — or a backgrounded tab — no longer shows the user as online; they age out
  once they stop interacting.
- **Search & filters on the admin user list** — the Operators tab gained a search
  box (username / email / name) and a filter popover (role, status, online-now,
  group), with an active-filter count and clear-all.
- **Notes open without the load pause** — the collaborative notes editor shows
  the note's content immediately (an instant preview while it connects, and no
  peer-sync wait when you're the only one on the note) and syncs in the
  background, instead of a ~1s "Loading note…" pause on every open.
- **Activity feed shows what changed in a note edit** — an edited note now
  renders a diff of just the changed lines (with a little context) instead of a
  bare "edited note content" line or the whole note.
- **Warn before editing a locked attachment** — opening the image/text/CSV
  editor on an attachment whose parent finding is VERIFIED now warns up front
  (the chain-of-custody lock would reject the save) so you can back out early.
- **Vault table view keeps the crack / wordlist actions** — the row action menu
  in the vault table now offers "Check Wordlist" and "Crack Hash" (for
  hash-shaped credentials), matching the card view.
- **Import source files are kept on record** — scanner imports and asset imports
  now auto-save the uploaded file to the engagement as an attachment (excluded
  from the report), and password-spray logs are auto-saved to the engagement
  vault (encrypted at rest, since they contain credentials). The upload screens
  note this.

### Fixed
- **Disabled plugins stay disabled after a restart** — the plugin loader now
  reads the saved enable/disable state at boot, so a plugin an admin disabled no
  longer re-enables itself when the containers restart or rebuild.
- **Tree view: drag a sub-test-case back to the top level** — in the Test Cases
  tab tree view you could drag an entry *onto* another to nest it, but there was
  no way to un-nest a child. Dragging now reveals a "Drop here to move to the top
  level" zone, so a child can be pulled back out to the root.
- **PDF report crash on some markdown content** — a field containing an
  identifier with an underscore or asterisk that appeared both in an emphasis
  span and in inline code (e.g. a service account like `svc_backup2` shown both
  in italics and in a `code` sample) could produce overlapping tags that crashed
  PDF generation with a 500. Inline markdown now renders such content safely.

## [1.5.5] — 2026-08-30

### Added
- **Interactive HTML report** — the HTML report format is now a portable,
  offline, self-contained interactive report: an Overview dashboard (risk
  posture, severity mix, key metrics, exposure-by-asset), filter/search/sort
  findings, a hierarchical test-case view, a **live attack graph** (with a
  per-finding "attack path"), an evidence gallery, and cleanup triage — all in
  three audience lenses (Executive / Security / Developer). It's a single
  `.html` file with everything embedded (data, images, fonts), so it opens by
  double-click and renders fully offline. Design spec + clickable prototype
  under `docs/report-redesign/`.
- **AI writing assistant in the editor** — an "Ask AI" panel on finding,
  test-case, asset, engagement, and note fields helps draft or edit the field
  you're on. It's grounded in the record (title, severity, CVSS, status), can
  look up how the same field reads in your other findings to match their style,
  and stays scoped to that one field rather than producing a whole write-up.
  Highlight text first and it rewrites just the selection (with a one-click
  "Replace selection"); otherwise it inserts at the cursor.
- **Readability review** — a **Review** button checks the current field for
  AI-slop and readability and returns concrete, field-scoped fixes (it never
  rewrites the field for you), using a bundled writing-review skill.
- **AI assistant on notes** — the collaborative notes editor gains the same
  Ask AI + Review assistant (hidden for read-only viewers).

### Improved
- **PDF report front-page dashboard + attack graphs** — the PDF now opens with a
  Risk Overview page mirroring the interactive report: the overall risk rating,
  a severity donut, key-metric tiles (findings / assets / test cases / fixed), a
  severity legend, and an exposure-by-asset chart. Each finding also carries an
  **attack path** diagram (test cases → finding → assets → cleanup), and small
  engagements get a full-engagement **attack graph** section. All rendered
  natively — no new dependencies.
- **Richer test cases in the PDF report** — the flat 4-column test-case table is
  replaced by a hierarchical detail view: the parent → child test tree, a
  pass/fail status chip, and markdown-rendered steps / expected result / actual
  result / notes, plus the findings each test discovered.
- **Resizable editors** — drag the bottom corner to resize the whole editor,
  and an inner handle to rebalance the editor against the AI panel without
  changing the overall size. AI replies now render as formatted markdown, and
  the assistant shows live "thinking" and data-lookup indicators.
- Editor toolbar icons now all have hover tooltips.
- **Paste a link onto selected text** — pasting an `http`/`https`/`mailto` URL
  while text is selected now turns the selection into a hyperlink instead of
  replacing it.

### Security
- **Template usage-counter endpoints now enforce the template visibility gate** —
  `POST /{template_id}/use` (finding + test-case templates) previously bumped the
  counter keyed only on the id with no visibility check, letting any authenticated
  user increment (and existence-probe via 200-vs-404) another user's non-published
  draft. It now 404s a template the caller can't see, like every other read.

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
- **Inline field editing on the test case and asset view pages** — extends the
  double-click-to-edit behaviour introduced for findings in 1.5.3 to test cases
  and assets. Test cases: title, description, execution steps, expected result,
  notes, category (searchable, colour-coded), and tags (multi-select dropdown).
  Assets: name, identifier (with a copy button), asset type (searchable, colour-
  coded), description, and notes. Each saves a single-field patch; editor-only,
  with an "add" affordance on empty optional fields.

### Improved
- **Test-case execution result** section restyled to match the app's theme (soft
  tinted Pass / Fail / No-Verdict buttons, a state-coloured result card), with
  tooltips explaining that pass/fail means the actual result matched — or didn't
  match — the expected result.

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
