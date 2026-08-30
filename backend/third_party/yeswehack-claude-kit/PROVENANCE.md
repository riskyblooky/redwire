# Provenance — yeswehack/claude-kit

| | |
|---|---|
| **Upstream** | https://github.com/yeswehack/claude-kit |
| **Path taken** | `skills/` (the `write`, `gotchas`, and `triage` skills) |
| **Commit** | `3928c3475bae5211835d05190d17fa1c445dd6f7` (branch `main`) |
| **Retrieved** | 2026-08-30 |
| **License** | GPL-3.0-only — see `./LICENSE` (verbatim upstream copy) |
| **Copyright** | © YesWeHack and the claude-kit contributors |

## What is vendored here (verbatim, unmodified)

```
skills/write/SKILL.md                    Bug-bounty report structure + per-section style
skills/gotchas/SKILL.md                  Per-vuln-class proof requirements + overclaim traps
skills/triage/SKILL.md                   Draft self-triage flow (READY / NEEDS FIXES / DO NOT SUBMIT)
skills/triage/references/ai-slop.md      AI-slop pattern checklist (human-readability review)
```

These files are copied **byte-for-byte** from the commit above. Do not edit
them here — if upstream changes are wanted, re-vendor from upstream and update
this file's commit hash and retrieval date.

## How RedWire uses them

RedWire's AI writing-assistance feature loads these skills from disk at
runtime (see `backend/utils/writing_skills.py`) and applies them as an
LLM **review** of the user's draft — flagging AI-slop / readability issues so
the author can fix them. The skills are used as-designed (they are reviewer
skills that critique but never rewrite). No text from these files is copied
into RedWire's own (Apache-2.0) source.

## License boundary

GPL-3.0-only is copyleft and is **not** the same license as RedWire
(Apache-2.0). These files stay GPL-3.0 and stay in this isolated directory.
If you redistribute RedWire, keep this directory, its `LICENSE`, and this
provenance file intact, and keep the `THIRD_PARTY_LICENSES.md` record at the
repo root accurate.
