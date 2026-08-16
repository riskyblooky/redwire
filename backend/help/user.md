# RedWire user guide

Everything an operator needs to run an engagement in RedWire — from scoping a
test through delivering the report. If you administer the platform (installs,
backups, integrations), see the **Admin guide** instead.

## The big picture

RedWire organizes work around **engagements**. An engagement is a single
assessment (a client, a scope, a timeframe, a team) and it owns everything you
produce during it: **findings**, **test cases**, **assets**, **evidence**,
**vault** items, **cleanup** artifacts, **notes**, and the **report**.

Almost every screen is scoped to the engagement you're currently in. Use the
engagement switcher in the top-left of the header to change context, or open an
engagement from the **Engagements** list.

## Working an engagement

Open an engagement to land on its **Overview**, then move through the tabs:

- **Overview** — status, dates, the team, quick counts, and a recent-activity
  feed. Snapshot of where the engagement stands.
- **Findings** — your vulnerabilities. Each is CVSS-scored and carries a
  severity (Critical / High / Medium / Low / Info), status, description,
  remediation, evidence, and links to the assets / test cases / vault items it
  relates to.
- **Test Cases** — the things you tried, pass/fail, organized as a tree. Link a
  test case to the findings it produced.
- **Assets** — hosts, services, URLs, and other targets in scope. Import them
  from a scan (see **Imports**) or add them by hand.
- **Attachments** — evidence files (screenshots, PCAPs, output) attached to the
  engagement, findings, or test cases.
- **Vault** — the credential vault: passwords, keys, tokens you recovered,
  encrypted at rest. Link a vault item to the finding or asset it came from.
- **Cleanup** — artifacts you dropped during the test (accounts, SSH keys, web
  shells) so nothing is left behind. Track each as Pending → Cleaned.
- **Notes** — free-form working notes with Markdown + Mermaid diagrams. Link a
  note to any finding, test case, asset, or vault item.
- **ATT&CK** — MITRE ATT&CK coverage mapped from your findings and test cases.
- **Activity** — a full audit stream of everything the team posted, with a
  **Feed** (readable, with content diffs) and a **Log** (raw table).
- **Reporting** — generate the deliverable (see **Reports**).

## Findings

The core of the work. To raise one, open **Findings → New Finding**:

1. **Title + description** — what it is and how to reproduce it. The editor
   supports Markdown, code blocks, inline images (paste a screenshot straight
   in), and Mermaid diagrams.
2. **Severity / CVSS** — set the CVSS vector; severity is derived from the
   score. Keep the vector consistent with what you describe.
3. **Remediation** — how the client fixes it.
4. **Link related work** — attach evidence, link the assets it affects, the
   test cases that found it, and any vault items or cleanup artifacts involved.
   These links show as chips in the Findings table's **Links** column.
5. **Status** — move it through your workflow (Open → … → Verified / Closed).

Findings have **version history** — every edit is snapshotted, and you can view
or **restore** a previous version from the finding's history.

## Evidence

Attach files to an engagement, a finding, or a test case. You can drag-and-drop,
use the shared dropzone, or **paste an image directly** from your clipboard.
Evidence can be flagged **include-in-report**, given a caption, and (for images)
you can inspect or **strip EXIF** metadata before it ships in a report.

## Notes, links, and chains

Notes are your scratch space, but they're also linkable — connect a note (or a
finding, test case, asset, vault item) to the things it relates to so the
picture stays joined-up.

**Attack chains** let you express cause → effect: "this misconfig led to that
credential, which led to that finding." Build them from the chain-link editor on
a finding, test case, or asset.

## Intelligence & Infrastructure

- **Intel** items (OSINT, threat intel, notes-from-the-field) can be linked to
  the findings and test cases they inform.
- **Infrastructure** items (your redirectors, C2, phishing infra) can be tracked
  and linked too, so the report can show the kit behind the test.

## Imports

**Imports** ingests scanner output and turns it into assets/findings. Nmap, Nessus,
Burp, and Nuclei are supported; Nmap imports also capture the exact command line
and scan metadata as a revisitable **scan history**. Start an import from the
engagement overview so it's pre-scoped, upload the file, review the **preview**,
then commit.

## Planning, scheduling & calendar

- **Planning** — an org-wide view of all engagements as a **Gantt** timeline or a
  **Calendar** month grid, with a date-range filter and a "jump to engagement"
  picker. Managers use it to see who's on what and spot scheduling clashes.
- **Scheduling** — find availability across the team for an engagement or date
  range, factoring in out-of-office.
- **Calendar** — your personal Day / Week / Month / Gantt view of assignments and
  out-of-office. Set your own OoO from here.

## Reports

Open **Reporting** on an engagement to generate the deliverable. Formats:

- **PDF** — the polished client report.
- **HTML** — a self-contained interactive report you can email or open offline.
- **JSON** — a structured export (includes entity relationships) for tooling.

Reports pull from the finding content, evidence flagged include-in-report,
classification / portion marking, and the report **theme** and **layout** you
pick. Templates for findings, test cases, runbooks, report layouts, and report
themes live under **Templates**.

## Notifications & email

The bell in the header shows in-app notifications (mentions, assignments,
automation actions). The full **Notifications** page lets you search, filter,
sort, and mark read/unread. In your **Profile** you can opt in to **email**
notifications and mute categories you don't care about.

## AI assistant

The in-app AI chat can answer questions about your engagements and run read-only
lookups on your behalf — it operates under **your** permissions, so it can only
see what you can see.

## Search & the command palette

- **Global search** (top of the app) spans engagements, findings, test cases,
  assets, notes, and comments.
- **Command palette** — press **Ctrl/Cmd-K** for quick navigation and create
  actions, plus vim-style key sequences (e.g. `g e` → engagements, `n f` → new
  finding).

## Your profile

Set your display name, photo, and password; enrol **TOTP** two-factor; manage
notification preferences; and record your skills (used by the growth-fit
matching on the planning page).

## Tips

- **@mention** teammates in comments and notes — they get a notification that
  deep-links back to the exact thread.
- Timestamps are shown in your local time throughout the app.
- The **What's New** entry in the user menu (bottom-left) shows recent release
  notes; the changelog lives at **/changelog**.
