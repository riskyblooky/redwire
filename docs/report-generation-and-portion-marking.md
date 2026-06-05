# Report Generation & Portion Marking — Design Spec

> **Implementation status (2026-06-04).** Phase A foundations + Phase B portion
> marking v1 are **implemented** on branch `feat/report-marking-and-control`
> and verified end-to-end (synthetic + real-data PDF generation; frontend
> typechecks clean). See "Implemented vs. deferred" at the bottom of this file.

Status: this is the reference doc for two related pieces of work:

1. **Deeper control over report appearance** (the "make other users' reports
   excellent" feedback item).
2. **Portion marking** following classification best practice (TLP 2.0 and
   IC/DoD base ladder), with configurable mark placement on images and tables.

It records the decisions already made in discussion so implementation can start
from a settled design.

---

## 0. Where we are today (baseline)

Appearance control is currently split across two objects, and almost everything
else is hardcoded in `backend/utils/report_generator.py`:

- **`ReportTheme`** (`backend/models/report_theme.py`) — 6 colors, `font_family`
  + body/heading sizes, `logo_base64`, `page_size`, `show_page_numbers`,
  `show_cover_page`, `cover_title`, `header_text`, `footer_text`.
- **`ReportLayout` / `ReportSection`** (`backend/models/report_layout.py`) — an
  ordered list of sections, each typed `TEXT | FINDINGS | TESTCASES |
  CLEANUP_ARTIFACTS` with a title and markdown content.
- Hardcoded in the generator: cover geometry (`_draw_cover`), finding-card field
  order (`_finding_card`), severity colors (`_SEV_COLORS` / `_SEV_BG_COLORS`
  module constants), the severity bar, the TOC (fake leader dots, no page
  numbers, no PDF outline), table styling (`#1E293B` / `#F8FAFC` / `#CBD5E1`
  repeated across three renderers), and evidence sizing.
- The **only** classification-like marking today is `footer_text` (default
  `"CONFIDENTIAL"`), a single document-wide string reused in the footer and the
  cover band.

Architecture decision: **keep the theme/layout split and deepen both; add a
third orthogonal object for marking** (rather than collapsing into one unified
template).

---

## 1. Appearance control — deepening theme & layout

Prioritized. Items 1–3 are the foundation and share a seam with portion marking
(the banner painter lives in the header/footer zones, so do them together).

### Phase A foundations
1. **TOC with real page numbers + PDF bookmarks/outline.** Replace the fake
   leader-dot TOC with ReportLab's `TableOfContents` flowable, and add a PDF
   outline pane via `canvas.bookmarkPage` / `addOutlineEntry`. Biggest usability
   win for long reports.
2. **Themeable severity colors + table style tokens.** Promote `_SEV_COLORS` /
   `_SEV_BG_COLORS` and the table grid/zebra colors out of module constants into
   theme fields. Align defaults with the frontend severity palette
   (Critical=red-500 … Info=slate-400 per `CLAUDE.md`).
3. **Header/footer zones + "Page X of Y".** Replace the single left-string +
   page-number footer with left/center/right zones, top and bottom, plus an
   optional per-page header logo. **Note:** the portion-marking banner (Part 2)
   paints *through* these zones — so the static `footer_text`-as-classification
   hack is removed here and superseded by the computed banner.
4. **Cover templates + metadata block.** Offer a few cover templates
   (`minimal`, `banded`, `full-bleed-image`, `classified`) instead of the
   hardcoded red-triangle geometry, plus an optional cover background image and a
   metadata block: report reference #, version, author/reviewer, engagement
   dates, distribution list, "prepared for / prepared by."

### Table styling (folds into item 2)
- **Odd/even row shading (zebra)** as an explicit toggle; shading colors as theme
  tokens. Currently hardcoded `ROWBACKGROUNDS [white, #F8FAFC]` in three places.

### Phase C (deep content control, later)
- **Per-section options** on `ReportSection`: page-break-before, start-on-odd,
  include/exclude.
- **Findings section controls:** which findings (filter by status/severity, e.g.
  exclude INFO or closed), grouping (by severity vs. by asset), and
  **finding-field selection / reorder / rename / custom fields** (CWE, OWASP
  category, remediation effort, status, CVSS sub-scores). The card's fields are
  hardcoded in `_finding_card` today.
- **New section/block types:** executive summary with auto risk-matrix /
  severity-donut / retest-status chart; appendix; methodology boilerplate; raw
  markdown block.
- **Custom/embedded TTF fonts** via `pdfmetrics.registerFont` (today only the 14
  standard PDF fonts work). Brand fonts, real monospace, non-Latin support.
- **DOCX / HTML export** alongside PDF/Markdown — clients often need an editable
  Word deliverable. Fits the existing `MarkdownReportGenerator` second-backend
  pattern.
- **Live preview / thumbnail** of the theme.

---

## 2. Portion marking

Best-practice lineages, **both** supported: **TLP 2.0** (FIRST.org — de-facto
standard in the security/CERT world) and **IC/DoD base ladder**
(`(U)/(C)/(S)/(TS)`). One engine, two rendering idioms keyed off a `scheme`
discriminator. **No dissemination-control modeling** (`//NOFORN`, `//REL TO`) —
the free-text suffix (§2.4) covers that for anyone who needs it.

### 2.1 The Marking Profile object

A sibling to `ReportTheme` / `ReportLayout`, selected per report.

**Shared core (both schemes):**
- `scheme` — `TLP_2.0 | IC_DOD | CUSTOM`.
- Ordered **levels**: `{ abbreviation, full_name, rank, banner_color,
  text_color }`. `rank` drives all roll-up.
- `enforcement` — `warn | block` (see §2.6 for how inheritance reframes this).
- Built-in TLP and IC level sets are seeded and immutable; `CUSTOM` profiles can
  define their own.

**Scheme-specific rendering:**

| | TLP 2.0 | IC / DoD |
|---|---|---|
| Built-in levels | RED `#FF2B2B`, AMBER+STRICT, AMBER `#FFC000`, GREEN `#33FF00`, CLEAR | (U), (C), (S), (TS) |
| Banner placement | Header, right-justified (FIRST spec) | Top **and** bottom, centered, bold, every page |
| Portion token | `TLP:AMBER` | `(S)` parenthetical at portion start |
| Roll-up | Document = highest TLP present | Banner = high-water mark of all portions |
| Cover extras | TLP definitions block | Classification authority + distribution statement |

### 2.2 Markable entities

A nullable, rank-ordered **`classification` = `{ level, suffix }`** (see §2.4) on:
engagement (default + ceiling — see §2.5), report section, finding, evidence,
testcase, cleanup artifact. `null` means **inherit** (see §2.5).

### 2.3 Images & tables — configurable placement

The differentiator. Placement is a **multi-select over a 3×2 grid + caption**:

```
 top-left      top-center      top-right
 bottom-left   bottom-center   bottom-right
 caption
```

- **Separate settings for images vs. tables** (same anchor model, independent
  values). "Top-left and bottom-right of each" = two anchors; "just top" = one;
  "just caption" = default.
- Lives on the **Marking Profile** as the document default; **per-entity
  override** is a later addition (ship profile-level first to avoid UI sprawl).
- A corner/caption mark shows the object's **rolled-up** mark (high-water of a
  table's cells; the image's own effective level). This is **distinct from
  per-row table marks**, which are a separate toggle — both can be on at once.
- **Images:** caption placement is trivial (text we already emit). Corner/edge
  overlays require wrapping the `Image` flowable in a small custom flowable that
  overprints the mark after drawing the bitmap. Same technique optionally stamps
  a detached-screenshot banner onto the image so it stays marked if extracted.
- **Tables:** rolled-up mark in the title/header; optional per-row mark column
  when rows differ in level.
- **Inline markdown images** pasted into a finding body have no row of their own
  → they **inherit the finding's effective mark** (decided; no per-image marking
  for inline images in v1).

### 2.4 Custom suffix — `(S//SAR/123)`

Classification is `{ level, suffix }`:
- `level` — base ladder value (`U/C/S/TS` or TLP level). **The only thing that
  drives ranking / roll-up.**
- `suffix` — free text appended verbatim → renders `(S//SAR/123)`. Carried
  through portion marks, captions, and corner overlays.
- **Escaping:** suffix is untrusted input reaching the PDF layer (Paragraph
  markup *and* image-overlay drawing) → must go through the generator's existing
  `_escape_xml` path.

### 2.5 Inheritance, ceiling, and the computed banner

Two mechanisms in opposite directions — keep them distinct:

**Inheritance (top-down default).** A portion's `classification` is optional;
`null` inherits. Resolution order per portion:

> **explicit mark → report default → engagement default → clamp to engagement
> ceiling**

A `(U)` image in an `(S)` report is just that image explicitly overridden to
`(U)`; everything else keeps inheriting. A portion **may be marked below** the
document default (the point of portion marking) but **never above the engagement
ceiling** — the one hard bound.

**Roll-up (bottom-up).** The **banner is computed, not set** — the highest
*effective* mark of any portion. The "report marking" the author sets is the
**default portions inherit**, which is *not* necessarily the banner:
- Default `(S)`, one image → `(U)` ⇒ banner still `(S)`.
- Default `(S)`, everything overridden → `(U)` ⇒ banner `(U)`.

So the **engagement carries two distinct values: a default** (what new portions
inherit) **and a ceiling** (max any portion may be set to).

**Open decision (v1 recommendation):** the banner shows the **highest base level
only**; suffixes/caveats stay per-portion. Full caveat roll-up (banner carries
the *union* of all caveats present, per strict classified practice) is noted as a
known simplification to revisit.

### 2.6 Enforcement / lint (reframed by inheritance)

Inheritance means "unmarked" is no longer a defect — it resolves to a default.
So enforcement becomes two softer checks:
- (a) every portion has an *effective* mark (always true once a default exists);
- (b) optionally **flag portions still riding the inherited default** so the
  author consciously confirms each one rather than rubber-stamping.

Plus a **classification legend** block and color-by-level banners.

---

## 3. How the two features intersect

The banner / portion-marking layer **reads from the Marking Profile but paints
through the theme's header/footer zones** — so appearance item A.3 is the shared
seam, and the banner supersedes today's `footer_text`-as-classification.

Generator gains a thin "marking" layer:
- high-water-mark computation run once before `doc.build()`;
- a banner painter in `_header_footer` / `_draw_cover`;
- a portion-mark prefix helper used by section headers, finding titles, captions,
  table headers/rows;
- the image-overlay custom flowable for corner/edge marks.

---

## 4. Phasing

- **Phase A — appearance foundations:** TOC page numbers + PDF bookmarks;
  themeable severity colors + table tokens (incl. zebra toggle); header/footer
  zones + "Page X of Y"; cover metadata block.
- **Phase B — portion marking v1:** Marking Profile (TLP + IC base ladder),
  `{level, suffix}`, per-entity classification, inherit-with-override + ceiling +
  computed banner, both rendering idioms, configurable image/table anchor
  placement (profile-level), per-row table marks, caption marks, cover legend +
  distribution statement, soft lint.
- **Phase C — deep control:** finding-field selection/reorder/custom fields,
  finding filtering/grouping, custom TTF fonts, cover templates, DOCX export,
  live preview, per-entity placement override.

---

## 5. Settled decisions (quick reference)

- Both TLP 2.0 **and** IC/DoD base ladder; one engine, `scheme` discriminator.
- IC base ladder only — no dissemination-control modeling (suffix covers it).
- Appearance: deepen theme/layout, add orthogonal Marking Profile (no unified
  template object).
- Classification = `{ level, suffix }`; only `level` ranks; suffix is free text,
  escaped.
- Mark placement: multi-select 3×2 grid + caption, separate for images vs.
  tables, profile-level default (per-entity override is Phase C).
- Per-row table marks: separate toggle, coexists with corner/caption marks.
- Table zebra shading: toggle + themeable colors.
- Inline markdown images inherit the finding's effective mark.
- `null` classification = inherit (explicit → report default → engagement default
  → clamp to ceiling).
- Engagement carries **default** and **ceiling** (distinct).
- Banner is computed (high-water), not set.
- v1 banner = highest base level only; caveat union roll-up deferred.
- Enforcement is soft (flag-default), not a hard block.

---

## Implemented vs. deferred (2026-06-04)

**Implemented (branch `feat/report-marking-and-control`):**
- `MarkingProfile` model/enums/schema/router (`/marking-profiles`), TLP 2.0 + IC/DoD seeded built-ins (read-only).
- `{classification_level, classification_suffix}` on finding/evidence/testcase/cleanup_artifact/report_section; engagement `marking_profile_id` + default + ceiling. Migrations `293665bb09ce` + `a1f2c3d4e5b6` applied.
- Generator (`utils/marking.py` + `report_generator.py`): inheritance + ceiling clamp, high-water banner roll-up, TLP header chip vs IC top+bottom banner, portion-marked section/finding/cleanup headers, evidence **image corner/edge/caption marks** (`MarkedImage`) + stamp toggle, table **caption mark lines + per-row mark column** + themeable zebra/grid, cover legend + distribution statement + metadata, themeable severity colors, header/footer L/C/R zones, **PDF bookmarks/outline**. Profile loaded in `reports.py` (config → engagement → default).
- Frontend: `use-marking-profiles` hook, marking-profile management page (`/templates/marking-profiles`), `ClassificationPicker`, engagement edit marking section (profile + default + ceiling), report-generate marking picker.

**Deferred (follow-ups):**
- Per-entity classification pickers on the finding / testcase / cleanup / evidence editors (today these inherit; only the engagement default + management UI are wired). The override scenario works in the generator — it just needs UI on each editor.
- Enforcement (`WARN`/`BLOCK`) is stored on the profile but **not yet enforced** at generation time (no pre-gen lint).
- Live TOC page numbers (multiBuild `TableOfContents`) and "Page X of Y" total count — current TOC kept; PDF outline added.
- Inline markdown images are not stamped (conceptually inherit the finding's mark).
- Cover templates beyond the existing one, custom TTF fonts, DOCX export, per-entity placement override (Phase C).
- Nav: the marking-profiles page is not yet linked from the templates hub / sidebar.
- One-off: an unrelated pre-existing schema drift (spray_*, *_attack_techniques, markdown_images indexes/FKs) surfaced during autogenerate and was intentionally left out — worth its own cleanup migration.

### Update (2026-06-04, follow-up pass)
Now also implemented:
- **Marking Profiles page linked in nav** — moved to top-level route `/marking-profiles` (avoids the `/templates` prefix double-highlight) with a sidebar entry (managerOnly). This is where all the fine placement controls live (image/table 3×2+caption anchors, per-row, stamp, legend, custom levels, enforcement, distribution).
- **Theme editor UI** for the deepened appearance fields: severity colors (5), table zebra toggle + alt-row + grid colors, header/footer L-C-R zones, cover subtitle/reference/version. (Only the generator-wired fields are exposed — `cover_template`, `cover_background_base64`, `show_page_x_of_y` columns exist but are intentionally not surfaced until the generator renders them.)
- **Per-entity classification pickers** on the finding, testcase, and evidence editors (backend `FindingUpdate`/`TestCaseUpdate`/evidence PATCH now accept `classification_level`/`classification_suffix`). A reusable `EntityClassificationField` resolves the engagement's active profile and renders the ladder. Still deferred: cleanup-artifact + report-section editors, and the inline detail-sheet editors (all inherit until set).

### Update (2026-06-04, batch 3)
Now implemented:
- **Per-entity classification on cleanup artifacts and report sections** (schemas + `ArtifactForm` picker + reporting-tab section editor; layout router carries section marks through).
- **Enforcement lint** at generation: `BLOCK` returns HTTP 400 listing portions with no effective mark (no explicit + no engagement default); `WARN` proceeds and surfaces a count of portions riding the inherited default via the `X-Marking-Warnings` response header → toast in the generate flow. CORS now exposes `Content-Disposition` + `X-Marking-Warnings`.
- **Live TOC** via reportlab `TableOfContents` + `multiBuild` + `afterFlowable` `TOCEntry` notifications (replaces the fake dot-leader table; real page numbers + dot leaders; the TOC's own header is excluded). **"Page X of Y"** via a counting canvas (`_make_numbered_canvas`), gated by the new `show_page_x_of_y` theme toggle (exposed in the theme editor), skipping the cover page.

Remaining deferred: cover templates beyond the current one, custom/embedded TTF fonts, DOCX/HTML export, inline-markdown-image stamping, and the separate cleanup migration for the unrelated spray_*/attack-technique/markdown_images drift.

### Update (2026-06-04, batch 4 — Phase C + loose ends)
Now implemented:
- **Cover templates** (`banded` / `minimal` / `full_bleed_image` / `classified`) + **cover background image** (base64, with a legibility scrim), wired into `_draw_cover` and exposed in the theme editor.
- **Inline markdown-image marking**: images pasted into finding / cleanup / text-section bodies now inherit the parent's effective mark and are stamped (corner overlay; CAPTION-only policies fall back to a TOP_LEFT stamp since inline images have no caption).
- **Per-section "start on a new page"** (`report_sections.page_break_before`, migration `f4a2c8e1d3b5`) honored in the generator + toggle in the reporting-tab section editor.
- **HTML export** (`HTMLReportGenerator`, uses the `markdown` lib): self-contained styled doc with base64-embedded evidence images, banner + portion marks + legend, severity/zebra theming. New `ReportFormat.HTML`; format picker + iframe preview in the reporting tab.
- **Schema-drift cleanup migration** (`b80ed9333c61`): aligned the pre-existing spray_*/attack-technique/markdown_images NOT NULL / index / FK drift; autogenerate is now clean.

Remaining Phase C (still deferred, lower priority): custom/embedded TTF fonts (needs regular+bold font upload), DOCX export (needs python-docx dep + image rebuild), finding field selection/reorder/custom-fields, findings grouping/filtering, exec-summary charts / appendix / methodology block types, and a live theme preview/thumbnail.

Operational note: applying b80ed9333c61 in dev surfaced lock contention from stale "idle in transaction" sessions — two concurrent `alembic upgrade` runs stacked on an ALTER TABLE. Resolved by terminating the stuck backends; run migrations one at a time.
