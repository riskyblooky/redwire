"""``_match_condition`` falls back to ``context["changes"]`` when the
post-update value isn't a top-level context key (GHSA-88hm-p8rq-cfw2
follow-up).

Before this PR, deleting the unsafe regex fallback left a real
regression: rules like "fire when engagement status flips to
COMPLETED" silently never matched because the engagement update
handler didn't populate ``status`` in top-level extra_context. The
new structured ``changes`` dict, produced by ``compute_changes_dict``
and consumed here, restores that matching.

These tests pin: top-level lookup still wins, changes-fallback fires
when top-level misses, and neither-present still returns False (same
as today).
"""

from __future__ import annotations

import pytest

from utils.automation_engine import _match_condition


# ── top-level still wins ───────────────────────────────────────────


def test_top_level_match_works_as_before():
    cond = {"field": "severity", "operator": "equals", "value": "critical"}
    ctx = {"severity": "critical"}
    assert _match_condition(cond, ctx) is True


def test_top_level_non_match_still_falsy():
    cond = {"field": "severity", "operator": "equals", "value": "critical"}
    ctx = {"severity": "low"}
    assert _match_condition(cond, ctx) is False


# ── changes-dict fallback ──────────────────────────────────────────


def test_changes_fallback_fires_when_field_missing_from_top_level():
    """The engagement update handler doesn't pass `status` in top-level
    extra_context — but compute_changes_dict puts the new value under
    `changes.status.new`. A rule like "engagement.updated where
    status=completed" should now match."""
    cond = {"field": "status", "operator": "equals", "value": "completed"}
    ctx = {
        "action": "updated_engagement",
        "changes": {"status": {"old": "in_progress", "new": "completed"}},
    }
    assert _match_condition(cond, ctx) is True


def test_changes_fallback_respects_negative_match():
    cond = {"field": "status", "operator": "equals", "value": "completed"}
    ctx = {
        "changes": {"status": {"old": "in_progress", "new": "reporting"}},
    }
    assert _match_condition(cond, ctx) is False


def test_top_level_value_beats_changes_dict():
    """If both are present, top-level wins. (Same key in both shouldn't
    happen in practice, but pinning the precedence so a future change
    doesn't silently flip it.)"""
    cond = {"field": "severity", "operator": "equals", "value": "critical"}
    ctx = {
        "severity": "critical",
        "changes": {"severity": {"old": "low", "new": "high"}},  # contradicts top-level
    }
    assert _match_condition(cond, ctx) is True


def test_neither_top_level_nor_changes_returns_false():
    cond = {"field": "nonexistent", "operator": "equals", "value": "x"}
    ctx = {"some_other_field": "y", "changes": {"another_field": {"new": "z"}}}
    assert _match_condition(cond, ctx) is False


def test_changes_with_missing_new_key_returns_false():
    """Defensive: if `changes.<field>` exists but has no `new` key
    (e.g. a redacted entry with `{"changed": True}`), the lookup
    should miss cleanly, not crash."""
    cond = {"field": "password", "operator": "equals", "value": "anything"}
    ctx = {"changes": {"password": {"changed": True}}}
    assert _match_condition(cond, ctx) is False


def test_changes_field_with_non_dict_value_is_ignored():
    """Robustness against malformed context — older events without the
    dict-of-dicts shape shouldn't blow up the engine."""
    cond = {"field": "status", "operator": "equals", "value": "x"}
    ctx = {"changes": {"status": "x"}}  # str, not dict
    assert _match_condition(cond, ctx) is False


def test_changes_key_absent_entirely():
    """No `changes` key at all is the normal pre-PR-6 shape — has to
    keep working for backwards compat."""
    cond = {"field": "severity", "operator": "equals", "value": "critical"}
    ctx = {"severity": "critical"}  # no `changes` key
    assert _match_condition(cond, ctx) is True


# ── operator coverage via the fallback path ────────────────────────


def test_contains_operator_works_via_changes_fallback():
    cond = {"field": "title", "operator": "contains", "value": "sql"}
    ctx = {"changes": {"title": {"old": "old", "new": "SQL Injection"}}}
    assert _match_condition(cond, ctx) is True


def test_numeric_gt_works_via_changes_fallback():
    """cvss_score lives in top-level extra_context for findings today,
    but a rule against any other numeric field would land via the
    fallback. Confirm numeric coercion still works."""
    cond = {"field": "cvss_score", "operator": "gt", "value": "7"}
    ctx = {"changes": {"cvss_score": {"old": 3.0, "new": 9.5}}}
    assert _match_condition(cond, ctx) is True
