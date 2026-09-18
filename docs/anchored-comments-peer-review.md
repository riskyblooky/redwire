# Anchored Peer-Review Comments

_Highlight a span of text inside a finding or test-case field and attach a
discussion thread to it — Google-Docs / Word-style inline comments, scoped to
peer review._

Status: design + plan. Targets a post-1.5.6 cycle.

---

## 0. TL;DR

- Reuse the existing **Thread / Comment** system. A "highlight comment" is just a
  `Thread` that additionally records **where in the text** it points.
- Highlights are shown only in an **annotation mode** — a TipTap/ProseMirror
  instance mounted over a field (entered by double-clicking the field, exactly
  like the current inline-edit affordance). Plain view mode stays a clean
  `MarkdownPreview` with no highlights.
- Highlights are **ProseMirror decorations**, not stored marks — they never touch
  the saved markdown, so report generation (PDF/HTML) is unaffected. This mirrors
  the existing `active-line-extension.ts`, which already builds a
  `DecorationSet` that survives re-renders.
- Persistence uses a **quote + context anchor** on the thread (W3C Web Annotation
  style) that is re-located to live ProseMirror positions when the editor mounts.
  During editing, ProseMirror's mapping keeps highlights glued to the text.
- Reviewers are frequently **non-owners without edit rights**, so annotation mode
  mounts a **read-only** editor for them — they can still see highlights and file
  comments (creating a comment does not modify the document).
- Unresolved anchored comments **surface a count** (per field / per finding). They
  do **not** block the Verified transition.

---

## 1. Scope

**In scope — all text (markdown) fields:**

| Resource  | Fields |
|-----------|--------|
| Finding   | `description`, `impact`, `technical_details`, `steps_to_reproduce`, `mitigations`, `references` |
| Test case | `description`, `steps`, `expected_result` |

Rendered by `InlineMarkdownField` → `MarkdownEditor` (TipTap) in edit,
`MarkdownPreview` (`@uiw/react-markdown-preview`) in view.

**Out of scope (v1):** notes (Yjs collaborative editor — different model), non-text
fields, cross-field selections, the report output itself.

---

## 2. Concepts & terminology

- **Anchor** — the stored description of *where* a thread points: which field, the
  quoted text, a little surrounding context, and an occurrence index.
- **Annotation mode** — a field rendered through TipTap (editable or read-only)
  with the comment-highlight decoration plugin active. The only place highlights
  render.
- **Decoration** — ProseMirror presentation layer applied on top of the document;
  does not mutate the doc or the saved markdown.
- **Orphaned anchor** — a thread whose quoted text can no longer be found in the
  current field content (the text was edited/deleted). Still listed, but detached
  from any highlight.

---

## 3. UX / interaction design

### 3.1 Entering annotation mode
- **Double-click a field** (already the inline-edit trigger). Behaviour by
  permission:
  - **Can edit** → editable TipTap + highlights (author revising while seeing
    review comments).
  - **Cannot edit** → read-only TipTap (`editable: false`) + highlights (reviewer
    annotating).
- A field with **any** anchored threads also shows a small always-visible affordance
  in view mode — a comment count chip (e.g. `💬 3`) in the field header — so
  reviewers know a clean-looking field has comments to open. Clicking it enters
  annotation mode.

### 3.2 Creating a comment
1. In annotation mode, select text. A floating **"Add comment"** button appears by
   the selection (model on existing selection affordances).
2. Click → composer opens (in the rail on the full page, or a popover in the sheet).
3. On submit → create a `Thread` anchored to the selection (field + quote +
   context + occurrence) with its first `Comment`. A highlight decoration appears
   immediately.
- Works for read-only reviewers (no document mutation involved).

### 3.3 Seeing comments — rail primary, hover secondary
- **Comments rail** (primary, full detail page): a panel beside the field/finding
  listing every anchored thread — quoted snippet, author, unresolved/resolved
  state, reply + resolve controls. **Bi-directional linking:**
  - Click a rail item → scroll to + **flash** its highlight.
  - Click a highlight → scroll the rail to + **expand** that thread.
- **Hover popover** (secondary): hovering a highlight shows a quick peek (first
  comment + count); click opens the full thread in the rail.
- **State styling:** active/selected highlight = stronger accent; unresolved =
  accent color; resolved = muted. Overlapping highlights stack (nested
  decorations); the count chip disambiguates.
- **Space constraint:** the full detail page has room for a persistent right rail.
  The 40vw side-sheet does not — there, use the hover popover + a collapsible
  "Comments (n)" list instead of a fixed rail.

### 3.4 Orphaned comments
- If a thread's quote can't be re-located (text edited away), it renders in the
  rail under an **"Outdated"** group showing the original quote, with reply/resolve
  still available, but no highlight. (Matches Google Docs behaviour.)

---

## 4. Permissions

- **View highlights / read threads:** anyone who can view the finding
  (`FINDING_VIEW` / test-case equivalent) — the same gate the Discussion section
  already uses.
- **Create anchored comment / reply / resolve:** same rules as the existing
  Thread/Comment endpoints (no new permission). Creating an anchor does **not**
  require field-edit rights, because it doesn't modify the document.
- **Edit the field text:** unchanged — still gated on `canEdit` (`useCanEdit`).

No new permission is introduced.

---

## 5. Data model

Add nullable columns to `threads` (all backfill-safe per the migration rules —
existing threads keep `NULL` and behave exactly as today):

| Column | Type | Notes |
|--------|------|-------|
| `anchor_field` | `String(64)` nullable | e.g. `"description"`; identifies which field the highlight is in. `NULL` = a plain (non-anchored) thread. |
| `anchor_quote` | `Text` nullable | The highlighted text as it read at creation. |
| `anchor_prefix` | `String(64)` nullable | Up to ~48 chars of text immediately before the quote (disambiguation). |
| `anchor_suffix` | `String(64)` nullable | Up to ~48 chars immediately after. |
| `anchor_occurrence` | `Integer` nullable | 0-based index of this quote among identical quotes in the field at creation (final tiebreaker). |
| `anchor_status` | `String(16)` nullable | `"active"` \| `"orphaned"`, maintained at read time; stored so the rail can group without re-computing. |

A thread is "anchored" iff `anchor_field IS NOT NULL`. Everything else about
Thread/Comment is unchanged.

Migration: single `alembic revision --autogenerate`, columns nullable, no
server_default needed. Rename to `YYYY-MM-DD_<revid>_add_thread_anchor.py`.

---

## 6. API changes

Minimal — extend the existing discussion router:

- `POST /threads` — accept optional `anchor` object
  (`field`, `quote`, `prefix`, `suffix`, `occurrence`). Validate that `field` is a
  legal field for the thread's `resource_type`. Persist onto the columns above.
- `GET /threads?resource_type=&resource_id=` — already filters by resource; return
  the anchor fields in `ThreadResponse` so the client can re-locate. Optionally
  accept `anchor_field=` to fetch just one field's anchored threads.
- `PUT /threads/{id}` — accept the same optional `anchor` block so the client can
  **auto-refresh** an anchor on save (§7.4). Anchor-only updates should not spam the
  activity log (skip the log when only anchor fields changed).
- No change to comments endpoints, resolve. A new anchored thread still logs
  `created` like any thread.

`ThreadResponse` gains an optional `anchor` block; absent for legacy threads.

---

## 7. Frontend architecture

### 7.1 Comment-highlight decoration extension
New TipTap extension `createCommentHighlightExtension(...)`, structured like
`active-line-extension.ts`:
- Holds a ProseMirror plugin whose state is a `DecorationSet`.
- Given the list of anchored threads for this field, it re-locates each quote to
  `{from, to}` positions and builds an **inline `Decoration`** with a class
  (`rw-comment-highlight`, plus `rw-resolved` / `rw-active` variants) and
  `data-thread-id`.
- On every transaction: `decorationSet.map(tr.mapping, tr.doc)` so highlights track
  edits live during the session.
- Thread-list changes (new comment, resolve, delete) are pushed in via a plugin
  `meta` (or an extension `storage` ref updated from React), triggering a recompute.

Highlights are **decorations only** — never the `Highlight` mark (which serializes
to markdown). This keeps `finding.description` etc. byte-identical and leaves the
PDF/HTML report generators untouched.

### 7.2 Position ↔ plain-text mapping
ProseMirror positions are structural, so map plain-text offsets to positions by
walking text nodes:
- `doc.descendants((node, pos) => …)` accumulating `node.text`, tracking a running
  plain-text offset; when the target offset falls inside a text node, the PM
  position is `pos + (targetOffset − nodeStartOffset)`.
- Map the quote's start and end offsets independently (a highlight may span
  multiple inline nodes, e.g. across a bold run).

### 7.3 Re-location algorithm (open / recompute)
Given a field's plain text `T` and an anchor `{quote, prefix, suffix, occurrence}`:
1. Find all indices where `quote` occurs in `T`.
2. **0 matches** → `orphaned`.
3. **1 match** → use it.
4. **>1 match** → score each by how much of `prefix` matches the chars immediately
   before and `suffix` the chars after; pick the best. On a tie, use the stored
   `occurrence` index; if that's out of range, fall back to the first.
5. Convert the chosen char range → PM positions (§7.2) → decoration.

Normalize whitespace consistently (collapse runs) on both store and lookup so
re-flowed markdown doesn't break matching.

### 7.4 Anchor lifecycle
- **Create:** from the current selection —
  `quote = doc.textBetween(from, to, ' ')`, `prefix`/`suffix` from the ~48 chars
  on either side, `occurrence` = count of identical quotes before `from`. POST.
- **Live (session):** decorations mapped through transactions; no writes.
- **Reopen:** re-locate from stored anchor (§7.3).
- **Save (auto-refresh):** when the field is saved, each still-matched anchored
  thread has its stored `quote`/`prefix`/`suffix`/`occurrence` recomputed from its
  current live mapped range and `PUT` back if changed. This keeps anchors fresh as
  the surrounding text drifts, so a highlight only orphans when its own text is
  actually deleted — not when text elsewhere in the field moved it. Threads already
  `orphaned` (quote not found) are left untouched.
- **Text edited so quote no longer matches:** `anchor_status = orphaned` on next
  read.

### 7.5 Components
- `useFieldThreads(resourceType, resourceId, field)` — TanStack hook, filters
  anchored threads for one field. Query key under `['threads', resourceType,
  resourceId]` so comment mutations invalidate cleanly.
- `<CommentRail>` — full-page rail; bi-directional linking to highlights (scroll +
  flash via the decoration/`data-thread-id` DOM node).
- `<CommentHoverCard>` — the peek popover.
- Extend `InlineMarkdownField` to accept `annotatable` + field identity and to host
  the decoration extension and the "Add comment" selection button.
- Count chip in each field header (`💬 n` unresolved), driven by `useFieldThreads`.

### 7.6 Count surfacing (decision #2)
- Per-field header chip: unresolved anchored count.
- Finding/test-case level: a rolled-up unresolved anchored count near the Peer
  Review panel (informational — **not** a gate on Verified).

---

## 8. Edge cases

- **Same quote twice in a field** → prefix/suffix, then `occurrence` (§7.3).
- **Overlapping / adjacent highlights** → nested inline decorations; rail + chip
  disambiguate.
- **Empty / unwritten field** → nothing to anchor; no chip.
- **Quote spans formatting** (bold/link/code) → start/end mapped independently
  (§7.2); the visible text is what's matched, so markdown syntax chars are never in
  the quote.
- **Very long selection** → cap stored `anchor_quote` length (e.g. 2 KB) but keep
  the full range for the live decoration in-session.
- **Reviewer with no edit rights** → read-only editor still paints decorations and
  allows comment creation.

---

## 9. Report generation

No impact. Highlights are decorations; stored markdown is unchanged; the PDF/HTML
generators read the same field strings they do today.

---

## 10. Rollout phases

1. **Backend:** anchor columns + migration; extend `POST /threads` and
   `ThreadResponse`.
2. **Decoration extension + mapping/re-location** (unit-testable against sample
   docs) — the riskiest logic, build and prove first.
3. **Annotation-mode wiring** in `InlineMarkdownField` (double-click, read-only vs
   editable, selection "Add comment").
4. **Comment rail + hover card + count chips**; bi-directional linking.
5. **Roll to all listed fields**; then the side-sheet compact variant.

---

## 11. Open questions / future

- "Jump to next unresolved comment" keyboard affordance.
- Whether resolved anchored threads should keep a faint highlight or disappear.
- Notes (Yjs) support — would use native collaborative marks, separate design.
