# RedWire user guide

Everything an operator needs to run an engagement in RedWire — from scoping a
test through delivering the report. If you administer the platform (installs,
backups, integrations), see the **Admin guide** instead.

## The big picture

RedWire organizes work around **engagements**. An engagement is a single
assessment (a client, a scope, a timeframe, a team) and it owns everything you
produce during it:

```mermaid
flowchart TD
    E["Engagement"] --> F["Findings"]
    E --> T["Test Cases"]
    E --> A["Assets"]
    E --> EV["Evidence"]
    E --> V["Vault"]
    E --> CL["Cleanup"]
    E --> N["Notes"]
    classDef eng fill:#6366f1,color:#0b1020,stroke:#4f46e5
    classDef find fill:#ef4444,color:#2a0606,stroke:#b91c1c
    classDef test fill:#10b981,color:#04231a,stroke:#047857
    classDef asset fill:#06b6d4,color:#042a33,stroke:#0e7490
    classDef eviden fill:#ec4899,color:#3a0824,stroke:#be185d
    classDef vault fill:#f59e0b,color:#3a2600,stroke:#b45309
    classDef clean fill:#84cc16,color:#1a2e05,stroke:#4d7c0f
    classDef note fill:#14b8a6,color:#04231f,stroke:#0f766e
    class E eng
    class F find
    class T test
    class A asset
    class EV eviden
    class V vault
    class CL clean
    class N note
```

Almost every screen is scoped to the engagement you're currently in. Use the
engagement switcher in the top-left of the header to change context, or open an
engagement from the **Engagements** list.

> <span class="rw-icon rw-icon-Lightbulb text-amber-400"></span> New here? Every
> page has a matching **?** button in the app header — click it for a quick
> explainer of what you're looking at.

## Working an engagement

Open an engagement to land on its **Overview**, then move through the tabs — the
icons and colours are the same ones you'll see in the app:

| Tab | What lives there |
|---|---|
| <span class="rw-icon rw-icon-LayoutDashboard text-slate-300"></span> **Overview** | Status, dates, the team, quick counts, and a recent-activity feed. |
| <span class="rw-icon rw-icon-Bug text-red-400"></span> **Findings** | Your vulnerabilities — CVSS-scored, with evidence and links. |
| <span class="rw-icon rw-icon-CheckSquare text-emerald-400"></span> **Test Cases** | What you tried, pass/fail, as a tree; linked to the findings they produced. |
| <span class="rw-icon rw-icon-Server text-cyan-400"></span> **Assets** | Hosts, services, URLs, and other in-scope targets. |
| <span class="rw-icon rw-icon-Paperclip text-pink-400"></span> **Attachments** | Evidence files (screenshots, PCAPs, output). |
| <span class="rw-icon rw-icon-Lock text-amber-400"></span> **Vault** | Recovered credentials, keys, and tokens — encrypted at rest. |
| <span class="rw-icon rw-icon-Sparkles text-lime-400"></span> **Cleanup** | Artifacts you dropped (accounts, keys, shells), tracked to *Cleaned*. |
| <span class="rw-icon rw-icon-StickyNote text-teal-400"></span> **Notes** | Free-form working notes with Markdown + Mermaid + links. |
| <span class="rw-icon rw-icon-Shield text-violet-400"></span> **ATT&CK** | MITRE ATT&CK coverage mapped from findings and test cases. |
| <span class="rw-icon rw-icon-Activity text-slate-300"></span> **Activity** | Audit stream of everything the team posted, with content diffs. |
| <span class="rw-icon rw-icon-FileText text-green-400"></span> **Reporting** | Generate the deliverable. |

Each tab loads its data on demand, and the count badges show live totals.

## <span class="rw-icon rw-icon-Bug text-red-400"></span> Findings

The core of the work. To raise one, open **Findings → New Finding**:

1. **Title + description** — what it is and how to reproduce it. The editor
   supports Markdown, code blocks, inline images (paste a screenshot straight
   in), and Mermaid diagrams.
2. **Severity / CVSS** — set the CVSS vector; severity is derived from the score.
3. **Remediation** — how the client fixes it.
4. **Link related work** — attach evidence, and link the assets, test cases,
   vault items, and cleanup artifacts involved. These show as chips in the
   Findings table's **Links** column.
5. **Status** — move it through your workflow (Open → … → Verified / Closed).

Findings keep full **version history** — every edit is snapshotted, and you can
view or **restore** a previous version.

**Severity at a glance** — the same colours the app uses everywhere:

| Severity | Rough meaning |
|---|---|
| <span class="text-red-500 font-bold">Critical</span> | Immediate, high-impact compromise. |
| <span class="text-orange-500 font-bold">High</span> | Serious issue, exploit likely. |
| <span class="text-yellow-500 font-bold">Medium</span> | Real risk, needs the right conditions. |
| <span class="text-blue-400 font-bold">Low</span> | Minor / limited impact. |
| <span class="text-slate-400 font-bold">Info</span> | Informational, no direct risk. |

## <span class="rw-icon rw-icon-Paperclip text-pink-400"></span> Evidence

Attach files to an engagement, a finding, or a test case. Drag-and-drop, use the
shared dropzone, or **paste an image straight from your clipboard**. Evidence can
be flagged **include-in-report**, captioned, and (for images) you can inspect or
**strip EXIF** metadata before it ships.

## <span class="rw-icon rw-icon-Link2 text-teal-400"></span> Links & chains

Two ways to connect things — they answer different questions.

**Links** are broad associations. From a finding, test case, asset, note, or
vault item you can link the things it relates to — the assets a finding affects,
the test cases that produced it, the evidence, notes, intel, and infrastructure
involved. They show as the icon chips in the **Links** column of each table and
keep the engagement joined-up. Links are symmetric: link a test case to a
finding and the finding shows the test case too.

**Chains** answer *"what led to what?"* — a directed **cause → effect** graph over
the three things that carry an attack narrative: **findings**, **test cases**,
and **vault items**. Each chain link is one arrow, "source **led to** target":

```mermaid
flowchart LR
    TC["Test Case: SMB relay"] -->|led to| F1["Finding: coerced NTLM auth"]
    F1 -->|led to| V["Vault: captured DA hash"]
    V -->|led to| F2["Finding: full domain compromise"]
    classDef tc fill:#6366f1,color:#0b1020,stroke:#4f46e5
    classDef fnd fill:#ef4444,color:#2a0606,stroke:#b91c1c
    classDef vlt fill:#eab308,color:#241d02,stroke:#a16207
    class TC tc
    class F1,F2 fnd
    class V vlt
```

Open the **chain editor** on a finding, test case, or vault item and you'll see
two lists: **Caused by** (what led to this) and what **this led to**. Add a step
in either direction, or **promote** something you've already *linked* straight
into the chain. Each directed pair links once; the reverse is its own link, so a
loop is always explicit.

These chains — together with your links — are what the engagement's **attack
graph** is built from (see *Reports*).

Notes, by the way, are fully linkable too: connect a note to any finding, test
case, asset, or vault item so your working thoughts stay attached to the work.

## Intelligence & Infrastructure

- <span class="rw-icon rw-icon-Radar text-violet-400"></span> **Intel** items
  (OSINT, threat intel) link to the findings and test cases they inform.
  Admin-configurable RSS feeds can pull in external sources.
- <span class="rw-icon rw-icon-Network text-teal-400"></span> **Infrastructure**
  items (redirectors, C2, phishing infra) can be tracked and linked, so the
  report shows the kit behind the test.

## <span class="rw-icon rw-icon-Upload text-primary"></span> Imports

**Imports** ingests scanner output into assets/findings — **Nmap, Nessus, Burp,
Nuclei**. Nmap imports also capture the exact command line and scan metadata as
revisitable **scan history**. Start from the engagement overview so it's
pre-scoped, upload the file, review the **preview**, then commit.

## <span class="rw-icon rw-icon-CalendarDays text-primary"></span> Planning, scheduling & calendar

- **Planning** — an org-wide view of every engagement as a **Gantt** timeline or
  a **Calendar** month grid, with a date-range filter and a *jump to engagement*
  picker. Colour-coded by status:

```mermaid
flowchart LR
    P["Proposed"] --> PL["Planning"] --> S["Scoping"] --> IP["In Progress"] --> R["Reporting"] --> C["Completed"]
    classDef proposed fill:#14b8a6,color:#04231f,stroke:#0f766e
    classDef planning fill:#f59e0b,color:#3a2600,stroke:#b45309
    classDef scoping fill:#06b6d4,color:#042a33,stroke:#0e7490
    classDef inprogress fill:#a855f7,color:#26073f,stroke:#7e22ce
    classDef reporting fill:#3b82f6,color:#0a1e4a,stroke:#1d4ed8
    classDef completed fill:#22c55e,color:#052e14,stroke:#15803d
    class P proposed
    class PL planning
    class S scoping
    class IP inprogress
    class R reporting
    class C completed
```

- **Scheduling** — find availability across the team for an engagement or date
  range, factoring in out-of-office.
- **Calendar** — your personal Day / Week / Month / Gantt view of assignments and
  out-of-office. Set your own OoO here.

## <span class="rw-icon rw-icon-FileText text-green-400"></span> Reports

Open **Reporting** on an engagement to generate the deliverable:

| Format | Best for |
|---|---|
| <span class="rw-icon rw-icon-FileText text-green-400"></span> **PDF** | The polished client report. |
| <span class="rw-icon rw-icon-Globe text-blue-400"></span> **HTML** | A self-contained interactive report you can email or open offline. |
| <span class="rw-icon rw-icon-Braces text-amber-400"></span> **JSON** | A structured export (with entity relationships) for tooling. |

Output honours the evidence you flagged include-in-report, classification /
portion marking, and the report **theme** + **layout** you pick — all of which
come from **Templates** (below).

The engagement also has a visual <span class="rw-icon rw-icon-Share2 text-primary"></span>
**attack graph** — a node-and-edge map of its assets, test cases, findings,
cleanup, and infrastructure, wired together by your links and the cause → effect
chains above. It's the picture that tells the "how we got in" story alongside the
written findings:

```mermaid
flowchart LR
    A["Asset: DC01"] -->|discovered| TC["Test Case: SMB relay"]
    TC -->|led to| F1["Finding: coerced NTLM auth"]
    F1 -->|led to| V["Vault: DA hash"]
    V -->|led to| F2["Finding: domain compromise"]
    F2 -->|affected| A
    classDef ast fill:#06b6d4,color:#042a33,stroke:#0e7490
    classDef tc fill:#6366f1,color:#0b1020,stroke:#4f46e5
    classDef fnd fill:#ef4444,color:#2a0606,stroke:#b91c1c
    classDef vlt fill:#eab308,color:#241d02,stroke:#a16207
    class A ast
    class TC tc
    class F1,F2 fnd
    class V vlt
```

## <span class="rw-icon rw-icon-BookOpen text-primary"></span> Templates

Templates let you standardise work so you're not rebuilding it every engagement.
The **Templates** hub has a tab per kind:

- <span class="rw-icon rw-icon-Bug text-red-400"></span> **Finding templates** —
  reusable finding content (title, category, description, impact, mitigations).
  When you raise a finding you can start from one to pre-fill it, then tailor.
- <span class="rw-icon rw-icon-CheckSquare text-emerald-400"></span> **Test-case
  templates** — reusable test cases to drop into an engagement.
- <span class="rw-icon rw-icon-GitBranch text-primary"></span> **Runbooks** — a
  curated set of test cases with a lifecycle (draft → published). **Apply** a
  runbook to an engagement to materialise its whole set of test cases at once, so
  every engagement of a given type starts with consistent coverage. Only
  published content applies.
- <span class="rw-icon rw-icon-FileText text-green-400"></span> **Report layouts**
  — the section structure and order of a report.
- <span class="rw-icon rw-icon-Sparkles text-lime-400"></span> **Report themes** —
  the visual styling (cover, fonts, colours) of a report.
- <span class="rw-icon rw-icon-Shield text-violet-400"></span> **Marking profiles**
  — classification / portion-marking sets applied to an engagement and carried
  into its reports.

**The flow:** build a template once → reuse it. Findings and test cases pull from
a template at create time; runbooks are *applied* to an engagement to materialise
test cases; layouts, themes, and marking profiles are chosen when you generate the
report.

## <span class="rw-icon rw-icon-Bell text-primary"></span> Notifications & email

The bell in the header shows in-app notifications (mentions, assignments,
automation actions). The full **Notifications** page lets you search, filter,
sort, and mark read/unread. In your **Profile** you can opt in to **email**
notifications and mute categories you don't care about.

## <span class="rw-icon rw-icon-Bot text-primary"></span> AI assistant

The in-app AI chat answers questions about your engagements and runs read-only
lookups for you — it operates under **your** permissions, so it can only see what
you can see.

## <span class="rw-icon rw-icon-Search text-primary"></span> Search & the command palette

- **Global search** (top of the app) spans engagements, findings, test cases,
  assets, notes, and comments.
- **Command palette** — press **Ctrl / Cmd-K** for quick navigation and create
  actions, plus vim-style key sequences (e.g. `g e` → engagements, `n f` → new
  finding).

## <span class="rw-icon rw-icon-UserCircle text-primary"></span> Your profile

Set your display name, photo, and password; enrol **TOTP** two-factor; manage
notification preferences; and record your **skills** (used by the growth-fit
matching on the planning page).

## Tips

- **@mention** teammates in comments and notes — they get a notification that
  deep-links back to the exact thread.
- Timestamps are shown in your **local** time throughout the app.
- The **What's New** entry in the user menu (bottom-left) shows recent release
  notes; the changelog also lives at **/changelog**.
