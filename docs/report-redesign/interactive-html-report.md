# Interactive HTML Report — Design Spec

Status: **design + clickable prototype** (2026-08-30). Not yet built into the
generator. The prototype is `./interactive-report-prototype.html` (open it in a
browser — dark by default, theme toggle, three audience lenses).

Goal: turn the HTML report from a static clone of the PDF into a **portable,
offline, interactive "report site"** — a standalone deliverable a client can
open off a USB stick and explore, with the depth each audience needs.

---

## 1. Packaging

A ZIP: one entry point + an assets tree.

```
redwire-report_<client>_<engagement>_<date>.zip
├── report.html                 # thin shell: <link css>, <script data>, <script app>
└── assets/
    ├── css/report.css
    ├── js/report.js            # the app (vanilla, no framework)
    ├── js/report-data.js       # window.__REPORT__ = { ...all data as JSON }
    ├── img/logo.png, evidence/<id>.png, …
    └── fonts/…                  # optional embedded brand fonts
```

**Why data-in-JS, images-as-files.** It must work by double-clicking `report.html`
off `file://`. Browsers block `fetch()` of local files, but `<script src>` and
`<img src>` with relative paths work. So report data rides in `report-data.js`
(`window.__REPORT__ = {…}`); images are real files. Zero CDN — everything
vendored. **Markdown is rendered server-side** (the existing Python `markdown`
lib) into HTML the app just styles, so no client markdown library ships.

**Separation.** The app (HTML/CSS/JS) is authored once and lives in the repo
(e.g. `backend/report_templates/interactive/`). The generator only injects
`report-data.js` + copies evidence images + stamps theme tokens, then zips.

---

## 2. The organizing idea — three audience *lenses*

Not three reports; three lenses over the same data with progressive disclosure.
A persistent switcher sets `body[data-audience]`; CSS shows/reorders depth
(`.depth-tech` is hidden for `exec`).

- **Executive** — one-screen posture: risk rating, severity mix, key metrics,
  top risks, remediation status. No CVSS vectors, no payloads.
- **Security** — full findings catalog + attack graph + evidence + full
  test-case execution detail (steps/expected/actual).
- **Developer** — remediation-first: exact repro, technical detail, payloads
  with copy, concrete fixes, grouped for fixing.

---

## 3. Sections (left-nav)

Overview · Findings · **Test Cases** · Attack Narrative · Assets · Evidence ·
Cleanup Triage · Scope & Method.

- **Overview** — risk hero (gauge + severity-mix bar + key metrics), metadata
  cover block, severity tiles (click → filter findings), **Exposure by asset**
  (findings/system stacked by severity), remediation status, top risks,
  timeline.
- **Findings** — search + severity/status filter chips + sort; expandable cards
  with layered disclosure (Description, Impact, Business impact, Affected
  assets, **Attack path** mini-graph, CVSS vector, Steps, Technical detail,
  Evidence, Remediation, References). Markdown-rendered fields.
- **Test Cases** — the hierarchical test plan (parent→child) with pass/fail
  status; Security/Developer lenses reveal steps/expected/actual/notes.
- **Attack Narrative** — the full interactive attack graph (below).
- **Cleanup Triage** — client-facing, so the client can verify artifact removal.

---

## 4. Attack graph (the reusable recipe)

Built from the **same node/edge shape as `GET /{eng}/attack-graph`**
(`backend/routers/attack_graph.py`):

- **Nodes:** `testcase` | `finding` | `asset` | `cleanup`.
- **Edges (kind):** `subtest` (tc→tc hierarchy), `discovered` (tc→finding),
  `affected`/`impacts` (finding↔asset), `targets`, `cleanup`. Cleanup anchors on
  its **linked asset** when one exists, else the finding.

**Rendering** (prototype = self-contained layered SVG, no library): longest-path
layered layout, left→right flow. Standard RedWire symbology so box types read at
a glance:

- **Box border = entity type:** asset **blue-400 `#60a5fa`**, test case
  **emerald-400 `#34d399`**, cleanup **lime-400 `#a3e635`**, finding = its
  severity color.
- **Icon = the rating:** finding by LMHC severity, test case by pass/fail
  (Pass green, Fail red, Executed muted). Icons are lucide (`Bug`,
  `CheckSquare`, `Server`, `Trash2`).

**Interaction:** hover to trace/highlight a node's path; click for a detail
popup with a contextual **"go to"** (open finding / open test case / open asset
/ go to cleanup); drag-to-pan the canvas. Shown as the Attack Narrative hero and
as a compact **per-finding attack path** inside each finding.

---

## 5. Theme / palette

RedWire tokens from `frontend/src/app/globals.css`: aurora dark surfaces
(`background 222 47% 4%`, `card 220 39% 11%`), foreground `210 40% 92%`,
**indigo-purple primary `263 70% 55%`** (red is Critical severity only).
Severity ramp = red-500 / orange-500 / yellow-500 / blue-400 / slate-400.
Entity colors as in §4. Dark default with a self-owned light toggle
(`data-report-theme`), independent of host. Fonts: Archivo (display), IBM Plex
Sans (body), IBM Plex Mono (data). A print stylesheet keeps it printable.

---

## 6. Backend generation plan

- New `ReportFormat.INTERACTIVE_HTML` → `InteractiveHtmlReportGenerator`
  emitting a ZIP (`application/zip`). The current single-file `HTMLReportGenerator`
  stays as "quick HTML."
- Reuse the already-loaded ORM data (findings incl. all fields, testcases,
  evidence, marking engine, theme tokens — all fetched in `reports.py` today),
  the marking/inheritance layer, and layout section-inclusion.
- Serialize → `report-data.js`; copy evidence bytes → `assets/img/`; stamp theme
  tokens as CSS vars + client logo; zip.
- **Preview constraint:** the in-app preview iframe is `sandbox=""`
  (`reporting-tab.tsx`), so interactive JS won't run in preview. Relax to
  `sandbox="allow-scripts"` for this format, or serve a static print-view
  fallback for preview and the full app in the download.

## 7. Phasing

1. Core site: Overview + Findings + Test Cases + Evidence + Cleanup + audience
   switcher + SVG charts + classification banners + print CSS + ZIP.
2. Attack graph, Assets matrix, deep-linking, keyboard nav.
3. Branding/cover options, accessibility audit, per-audience export.
