"""Runtime loader for the bundled third-party writing-review skills.

The skill content lives under ``backend/third_party/yeswehack-claude-kit/``
(GPL-3.0-only, kept isolated — see that directory's ``LICENSE`` and
``PROVENANCE.md``). This module is RedWire's own code (Apache-2.0). It only
*loads* those files from disk at runtime and hands their text to the AI review
prompt — it must never embed their text.

License boundary rule: read the guidance from the files, never paste any of
their prose into this source. That keeps the Apache-2.0 code free of GPL text
and the GPL content confined to its directory, used purely as runtime data.
"""
from __future__ import annotations

import os
from functools import lru_cache

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_SKILLS_ROOT = os.path.normpath(
    os.path.join(_THIS_DIR, "..", "third_party", "yeswehack-claude-kit", "skills")
)

# Logical name → file on disk. Only the readability checklist is used for the
# review today; the others are available for future use (structure / class
# gotchas) without re-vendoring.
_SKILL_FILES = {
    "ai_slop": os.path.join(_SKILLS_ROOT, "triage", "references", "ai-slop.md"),
    "write": os.path.join(_SKILLS_ROOT, "write", "SKILL.md"),
    "gotchas": os.path.join(_SKILLS_ROOT, "gotchas", "SKILL.md"),
    "triage": os.path.join(_SKILLS_ROOT, "triage", "SKILL.md"),
}


@lru_cache(maxsize=None)
def _read(name: str) -> str:
    """Read one bundled skill file; empty string if it isn't present (so a
    deploy missing the third_party tree degrades gracefully rather than 500s)."""
    path = _SKILL_FILES.get(name)
    if not path or not os.path.isfile(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def _strip_frontmatter(text: str) -> str:
    """Drop a leading ``---\\n…\\n---`` YAML block (Claude-skill metadata) if
    present — it's noise inside an LLM prompt."""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            nl = text.find("\n", end + 1)
            if nl != -1:
                return text[nl + 1:].lstrip("\n")
    return text


def review_skills_available() -> bool:
    """True when the bundled readability checklist is on disk and loadable."""
    return bool(_read("ai_slop").strip())


# What each editable field is actually FOR, so the review judges the field on
# its own purpose instead of demanding whole-report content (PoC payloads,
# reproduction steps, CVSS, remediation, report sections) that lives in other
# fields. Keys are normalized field names (lower-cased, spaces→underscores).
_REVIEW_FIELD_PURPOSE: dict[str, dict[str, str]] = {
    "finding": {
        "description": "a brief, factual statement (1-3 sentences) of what the vulnerability is and where",
        "impact": "what was actually demonstrated to be at risk, stated from the evidence",
        "steps_to_reproduce": "atomic, ordered reproduction steps (with preconditions) a reader can follow verbatim",
        "technical_details": "the technical mechanism / root cause plus supporting request-response detail",
        "mitigations": "concrete remediation specific to this bug",
        "references": "external pointers only (advisories, write-ups)",
    },
    "testcase": {
        "description": "a short statement of what this test case checks",
        "steps": "the ordered execution steps for the test",
        "expected_result": "what a passing / expected outcome looks like",
        "actual_result": "what was actually observed when the test ran",
        "notes": "supplementary notes for the test case",
    },
    "engagement": {
        "description": "a short overview of the engagement",
        "scope": "what is in and out of scope",
        "objectives": "the goals of the engagement",
    },
    "asset": {
        "description": "a short description of the asset",
        "notes": "supplementary notes about the asset",
    },
}


def _field_scope_clause(resource_type: str, field_name: str) -> str:
    """Field-scoping guidance for the reviewer: what this field is for, and an
    explicit instruction not to flag it for content that belongs in sibling
    fields of the same record."""
    rt = resource_type.strip().lower().replace(" template", "")
    fn = field_name.strip().lower().replace(" ", "_")
    purpose = _REVIEW_FIELD_PURPOSE.get(rt, {}).get(fn)
    purpose_line = f'This field should contain {purpose}. ' if purpose else ""
    return (
        f'FIELD SCOPE (important): you are reviewing ONLY the "{field_name}" field, which is one '
        f'part of a larger {rt} record. {purpose_line}Other content — proof-of-concept payloads, '
        "reproduction steps, request/response detail, CVSS or severity scoring, remediation, and "
        "report sections like Introduction or Summary — lives in SEPARATE fields of the record and is "
        f'not this field\'s job. Do NOT flag the "{field_name}" for missing anything that belongs to '
        "those other fields, and do not tell the author to add sections or structure to it. Judge only "
        f'whether the "{field_name}" text itself is well-written, honest, and slop-free for its own purpose.\n\n'
    )


def build_review_system_prompt(resource_type: str, field_name: str, draft: str) -> str:
    """Build the reviewer system prompt for a readability / AI-slop pass over a
    draft. The checklist body comes verbatim from the bundled GPL skill file
    (loaded at runtime); the RedWire framing and output contract around it are
    RedWire's own.
    """
    checklist = _strip_frontmatter(_read("ai_slop")).strip()
    draft = (draft or "").strip() or "(empty)"
    return (
        f'You are a strict senior reviewer checking a RedWire {resource_type} draft '
        f'(the "{field_name}") for AI-slop and human readability.\n\n'
        + _field_scope_clause(resource_type, field_name) +
        "Apply the checklist below to the DRAFT and report what a careful human "
        "reviewer would catch, so the author can fix it. Do NOT rewrite the draft — "
        "point to each concrete issue and give a specific, actionable fix.\n"
        "This is an internal red-team finding inside RedWire, not a YesWeHack bug-bounty "
        "submission: ignore checklist items about program scope, rules of engagement, or "
        "a submission form, and focus on readability, honest evidence-based impact, and "
        "AI-slop tells. Apply a checklist item ONLY when it concerns what THIS field is "
        "meant to contain (per FIELD SCOPE above); skip items that are really about other "
        "fields of the record.\n\n"
        "Return EXACTLY this shape (omit an empty severity section, but always include "
        "VERDICT and What's good):\n"
        "VERDICT: READY | NEEDS FIXES | NOT READY\n"
        "## Critical (must fix)\n- <issue> → <fix>\n"
        "## Strong (should fix)\n- <issue> → <fix>\n"
        "## Minor (cleanup)\n- <issue> → <fix>\n"
        "## What's good\n- <things worth keeping>\n\n"
        "If the draft is clean, say so plainly — do not invent issues or pad with caveats.\n\n"
        "=== READABILITY / AI-SLOP CHECKLIST ===\n"
        f"{checklist}\n"
        "=== END CHECKLIST ===\n\n"
        "=== DRAFT TO REVIEW ===\n"
        f"{draft}\n"
        "=== END DRAFT ==="
    )
