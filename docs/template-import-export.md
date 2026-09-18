# Template & Runbook Import / Export — Design

Status: **DESIGN ONLY (not implemented)**. Captured 2026-08-19 for later work.

## Goal

Add **Import** and **Export** to the Template Library (`/templates`) for the three
shareable template types:

- **Finding templates**
- **Test-case templates**
- **Runbooks** — exporting a runbook must also carry the **test-case templates**
  it references; importing one must **reuse test-case templates that already
  exist** (matched by name) rather than duplicating them.

On import: **dupe-check by name**, show a **diff** for conflicts, and let the
user choose **which to keep** (existing vs. imported) per item.

## Data model (today)

| Type | Name key | Content fields | Relationships |
|---|---|---|---|
| `FindingTemplate` | `title` | `category`, `description`, `impact`, `mitigations`, `references`, `attack_technique_ids[]`, `status` | — |
| `TestCaseTemplate` | `title` | `category`, `description`, `steps`, `expected_result`, `attack_technique_ids[]`, `status` | — |
| `Runbook` | `name` | `description`, `runbook_type`, `status` | `RunbookItem[]` |
| `RunbookItem` | — | `sort_order` | `template_id → testcase_templates`, `parent_id → runbook_items` (tree) |

Notes:
- `status ∈ {DRAFT, SUBMITTED, PUBLISHED}`; visibility = PUBLISHED to all, own
  DRAFTs to the creator, SUBMITTED to managers.
- `RunbookItem` forms a **tree** via `parent_id` + `sort_order`. Creation uses
  `temp_key` / `parent_temp_key` to rebuild the tree in one POST
  (`RunbookItemCreate`).
- Manage roles: `ADMIN`, `READ_ONLY_ADMIN`, `TEAM_LEAD` (`_can_manage`).
- List endpoints already support `q`/`category`/`status`/`skip`/`limit` +
  `X-Total-Count` (added for the paged Template Library).

## Export format (portable JSON)

Single self-describing document. `type` drives which arrays are populated.
Runbook exports embed the referenced test-case templates so an import on a
fresh instance can recreate anything missing.

```json
{
  "kind": "redwire-template-export",
  "version": 1,
  "type": "finding | testcase | runbook",
  "exported_at": "2026-08-19T00:00:00Z",

  "finding_templates": [
    { "title": "...", "category": "...", "description": "...",
      "impact": "...", "mitigations": "...", "references": "...",
      "attack_technique_ids": ["T1059"] }
  ],

  "testcase_templates": [
    { "title": "...", "category": "...", "description": "...",
      "steps": "...", "expected_result": "...",
      "attack_technique_ids": ["T1595"] }
  ],

  "runbooks": [
    { "name": "...", "description": "...", "runbook_type": "...",
      "items": [
        { "template_title": "Port scan", "sort_order": 0, "children": [
          { "template_title": "Service enum", "sort_order": 0, "children": [] }
        ] }
      ] }
  ]
}
```

Rules:
- Runbook `items` are a **nested tree**; each node references its test-case
  template **by `template_title`** (not id — ids aren't portable across
  instances). The full defs of every referenced test case go in
  `testcase_templates` so the importer can create any that are missing.
- Export omits per-instance/workflow fields: `id`, `status`, `submitted_at`,
  `published_*`, `review_note`, `created_by`, timestamps. Imported rows get a
  fresh identity.
- Export scope: everything the caller can **see** (PUBLISHED + own). Reasonable
  default; a future "selected only" mode can pass ids.

## Backend — unified transfer router

New `routers/template_transfer.py`, `prefix="/template-transfer"`, registered in
`main.py`. Three endpoints, `type`-driven.

### `GET /template-transfer/export?type=finding|testcase|runbook`
- Auth: any authenticated user (exports what they can see).
- Builds the JSON above. For `runbook`: flat `RunbookItem`s → nested tree
  (`parent_id` + `sort_order`), collect referenced test cases into
  `testcase_templates`.
- Returns JSON; frontend downloads it as a `.json` blob.

### `POST /template-transfer/import/preview`
- Body: the exported document.
- Auth: **manage roles only** (import writes shared templates).
- Match **by name** (`title` / `name`), case-insensitive/trimmed.
- Returns a preview the UI renders:

```json
{
  "type": "finding",
  "items": [
    { "name": "SQLi", "action": "new",       "incoming": { ...fields } },
    { "name": "XSS",  "action": "identical",  "existing_id": "..." },
    { "name": "IDOR", "action": "conflict",   "existing_id": "...",
      "diff": { "description": { "old": "...", "new": "..." },
                "impact":      { "old": "...", "new": "..." } },
      "incoming": { ...fields } }
  ]
}
```

For `type=runbook` the preview has two sections:

```json
{
  "type": "runbook",
  "testcases": [
    { "title": "Port scan",    "action": "exists" },
    { "title": "New enum step", "action": "new" }
  ],
  "runbooks": [
    { "name": "External Recon", "action": "new" },
    { "name": "Web App",        "action": "conflict", "existing_id": "..." }
  ]
}
```

`action` values: `new` (create), `identical` (all fields equal — skip silently),
`conflict` (same name, ≥1 field differs — user decides), `exists` (runbook
test-case already present — reuse).

### `POST /template-transfer/import`
- Body: the exported document **+ decisions**:
  `{ "decisions": { "<name>": "keep_existing" | "replace" }, ... }`
  (default for unspecified conflicts: `keep_existing`).
- Auth: manage roles.
- Apply, all in one transaction:
  - **new** → create (status `PUBLISHED`, `created_by = importer`).
  - **conflict + replace** → overwrite the existing row's content fields.
  - **conflict + keep_existing** / **identical** → skip.
  - **Runbook**:
    1. For each referenced test-case (`testcase_templates`): match existing by
       `title` → **reuse its id**; else create it (respecting its own decision).
    2. Resolve every `items[].template_title` → a real `template_id` from step 1.
    3. Runbook by name: `new` → create with the item tree (mirror
       `create_runbook`'s `temp_key`/`parent_temp_key` build); `conflict +
       replace` → replace items; `keep_existing` → skip.
- Returns counts: `{ created, updated, skipped, testcases_created, testcases_reused }`.

### Field-diff helper
Reuse the shape of `compute_changes_dict` (`{field: {old, new}}`) but comparing
**existing vs. incoming** content fields only (ignore workflow/identity fields).
`identical` when the diff is empty.

## Frontend — Template Library UI

### Buttons
Per tab (Findings / Test Cases / Runbooks) header, next to "New Template":
- **Export** (`Download` icon) → `GET export?type=…` → save `redwire-<type>-templates.json`.
- **Import** (`Upload` icon) → hidden `<input type=file accept=.json>` → read →
  `POST import/preview` → open the **Import Review** modal.

### Import Review modal
- **Summary chips**: `N new · M conflicts · K identical` (+ for runbooks:
  `X test cases new · Y reused`).
- **Conflicts list**: each row = name + a compact **field diff** (old → new,
  reuse `computeLineDiff` used in the Activity feed) + a **toggle**:
  `Keep existing` ⟷ `Replace with imported` (default *Keep existing*).
- **New list**: collapsed count (all created; no decision needed).
- **Runbook mode**: also show the test-case section (new vs. reused) so the user
  sees that existing test cases are reused, not duplicated.
- Footer: `Import N items` → `POST import` with decisions → toast summary →
  invalidate the relevant query keys (`finding-templates-paged`,
  `testcase-templates-paged`, `runbooks-paged`, and the grand-total queries).

### Reuse
- Diff rendering: `computeLineDiff` (already used by the Activity feed).
- File download: Blob + object URL (same pattern as other JSON exports).

## Permissions
- **Export**: any authenticated user.
- **Import (preview + apply)**: manage roles only (`ADMIN`, `TEAM_LEAD`; not
  `READ_ONLY_ADMIN` for apply since it writes). Preview may allow
  `READ_ONLY_ADMIN`.

## Edge cases / decisions
- **Name match** is case-insensitive + trimmed; exact-name only (no fuzzy).
- **Test-case category** is required on the model — importing a test case (incl.
  via runbook) must carry a `category`; reject/skip with a clear error if absent.
- **attack_technique_ids** copied as-is (plain MITRE ids; portable).
- **Dangling runbook item**: an item whose `template_title` isn't in the
  document's `testcase_templates` **and** doesn't exist → skip that node, warn.
- **Import status**: created rows are `PUBLISHED` (they're being shared as
  ready-to-use). Alternative: import as `DRAFT` owned by importer — decide before
  building.
- **Large imports**: cap items (reuse `MAX_RUNBOOK_ITEMS` / a list cap) and wrap
  apply in a single transaction so a partial failure rolls back.

## Open questions (resolve before building)
1. Imported template **status**: `PUBLISHED` vs `DRAFT`-owned-by-importer?
2. Conflict granularity: **per-item** keep/replace (this design) vs. per-field
   merge (more work — probably not worth it).
3. Export scope: all-visible (this design) vs. "export selected/filtered set".
4. Should Export respect the current tab's active search/filters?
