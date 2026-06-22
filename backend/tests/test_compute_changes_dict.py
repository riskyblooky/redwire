"""``compute_changes_dict`` regressions (GHSA-88hm-p8rq-cfw2 follow-up).

GHSA-88hm deleted the unsafe regex fallback in ``_match_condition``
that scraped post-update values out of the prose ``build_change_summary``
string. ``compute_changes_dict`` is the structured replacement: it
produces a ``{field: {"old": ..., "new": ...}}`` dict that the
automation engine consults via ``context["changes"]`` when the
top-level extra_context doesn't carry the field.

These tests pin the contract: which fields land in the dict, which
get redacted, and how enum values get normalised so the
automation-engine lookup produces the same scalar shape the routers
already pass at the top level (``finding.severity.value.lower()`` etc).
"""

from __future__ import annotations

import enum
import types

import pytest

from utils.collaboration import compute_changes_dict, _normalize_for_match


class _Sev(str, enum.Enum):
    LOW = "low"
    CRITICAL = "critical"


def _obj(**kwargs):
    """Tiny stand-in for an ORM/Pydantic object — just attribute access."""
    return types.SimpleNamespace(**kwargs)


# ── compute_changes_dict ────────────────────────────────────────────


def test_skips_unchanged_fields():
    old = _obj(title="X", status="open")
    update = {"title": "X", "status": "closed"}
    assert compute_changes_dict(old, update) == {
        "status": {"old": "open", "new": "closed"},
    }


def test_missing_old_attribute_is_treated_as_none():
    old = _obj(title="X")  # no `status` attribute at all
    update = {"status": "open"}
    assert compute_changes_dict(old, update) == {
        "status": {"old": None, "new": "open"},
    }


def test_empty_update_data_returns_empty_dict():
    assert compute_changes_dict(_obj(title="X"), {}) == {}


def test_none_to_value_is_a_change():
    old = _obj(description=None)
    update = {"description": "now set"}
    assert compute_changes_dict(old, update) == {
        "description": {"old": None, "new": "now set"},
    }


def test_value_to_none_is_a_change():
    old = _obj(description="was set")
    update = {"description": None}
    assert compute_changes_dict(old, update) == {
        "description": {"old": "was set", "new": None},
    }


def test_redacted_fields_appear_as_changed_flag_only():
    """Vault-encrypted fields must not leak old/new values into the
    automation context — that's the same redaction discipline
    ``build_change_summary`` uses. The redacted set covers
    ``username``, ``password``, ``note`` (the three vault columns
    encrypted at rest). Other fields stay un-redacted."""
    old = _obj(password="old_ciphertext", username="alice", name="VPN-prod")
    update = {"password": "new_plaintext", "username": "bob", "name": "VPN-stage"}
    out = compute_changes_dict(old, update)
    assert out["password"] == {"changed": True}
    assert out["username"] == {"changed": True}  # also vault-encrypted
    # ``name`` is metadata, not credentials — old/new survive.
    assert out["name"] == {"old": "VPN-prod", "new": "VPN-stage"}


def test_redacted_field_appears_even_when_old_equals_new():
    """For redacted fields we can't compare old/new (one's ciphertext,
    one's plaintext), so we always surface them when they're in the
    update payload — same shape as build_change_summary."""
    old = _obj(password="ciphertext")
    update = {"password": "same-plaintext-could-be-anything"}
    out = compute_changes_dict(old, update)
    assert "password" in out
    assert out["password"] == {"changed": True}


# ── enum normalisation ──────────────────────────────────────────────


def test_enum_old_value_is_coerced_to_underlying_value():
    """A condition like `severity equals critical` is what rule authors
    write. The routers explicitly do `finding.severity.value.lower()`
    when populating top-level extra_context. The changes dict has to
    match that scalar shape, or the fallback lookup compares
    "Severity.CRITICAL" (enum repr) against "critical" and fails."""
    old = _obj(severity=_Sev.LOW)
    update = {"severity": "critical"}
    out = compute_changes_dict(old, update)
    assert out["severity"]["old"] == "low"
    assert out["severity"]["new"] == "critical"


def test_enum_new_value_is_coerced():
    """update_data might carry an enum object (Pydantic might or might
    not have coerced) — normalise either way."""
    old = _obj(severity="low")
    update = {"severity": _Sev.CRITICAL}
    out = compute_changes_dict(old, update)
    assert out["severity"]["new"] == "critical"


def test_normalize_for_match_passes_through_scalars():
    assert _normalize_for_match("hello") == "hello"
    assert _normalize_for_match(42) == 42
    assert _normalize_for_match(True) is True
    assert _normalize_for_match(None) is None
    assert _normalize_for_match([1, 2]) == [1, 2]


def test_normalize_for_match_unwraps_enum():
    assert _normalize_for_match(_Sev.CRITICAL) == "critical"
