"""Regressions for the stats scope-mode toggle that controls what the
/analytics/* and /stats/* endpoints expose to non-admin callers.

GHSA-ffmc-hrp8-hhj7 shipped engagement-scoped stats for non-admins.
The toggle adds a second mode ("global") that lets non-admins see
platform-wide aggregates — but the handler MUST receive
``strip_identifiers=True`` in that mode so the response anonymises
engagement / client / user names. These tests pin the three pieces
of contract the helper has to honour: admin always wins, mode is
consulted only in the no-engagement-id path, and engagement-id
membership 403s regardless of mode.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from auth import rbac
from auth.rbac import apply_stats_scope, get_stats_scope_mode
from models.user import UserRole


# ── fakes ────────────────────────────────────────────────────────────


class _FakeScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalar(self):
        return self._value


class _FakeDb:
    """Single-purpose AsyncSession fake. Each ``execute`` call returns
    whichever value was queued; tests queue values in the order the
    helper will pull them so they don't have to inspect SQL."""

    def __init__(self, results):
        self._results = list(results)

    async def execute(self, _query):
        if not self._results:
            return _FakeScalarResult(None)
        return _FakeScalarResult(self._results.pop(0))


def _user(role: UserRole, user_id: str = "u-1"):
    return SimpleNamespace(id=user_id, role=role)


# ── admin always sees everything ─────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_no_engagement_returns_global_no_strip():
    """Admin asking for global stats: full data, never stripped."""
    db = _FakeDb([])  # no DB lookups expected
    is_admin, _subq, strip = await apply_stats_scope(
        None, db, _user(UserRole.ADMIN)
    )
    assert is_admin is True
    assert strip is False


@pytest.mark.asyncio
async def test_admin_with_engagement_no_strip():
    db = _FakeDb([])
    is_admin, _subq, strip = await apply_stats_scope(
        "eng-1", db, _user(UserRole.ADMIN)
    )
    assert is_admin is True
    assert strip is False


@pytest.mark.asyncio
async def test_team_lead_treated_as_admin():
    """TEAM_LEAD is in _ADMIN_ROLES — bypasses both the membership
    check and the mode toggle. Same posture as ADMIN."""
    db = _FakeDb([])
    is_admin, _subq, strip = await apply_stats_scope(
        None, db, _user(UserRole.TEAM_LEAD)
    )
    assert is_admin is True
    assert strip is False


@pytest.mark.asyncio
async def test_read_only_admin_treated_as_admin():
    db = _FakeDb([])
    is_admin, _subq, strip = await apply_stats_scope(
        None, db, _user(UserRole.READ_ONLY_ADMIN)
    )
    assert is_admin is True
    assert strip is False


# ── engagement_id path: membership check + 403 ──────────────────────


@pytest.mark.asyncio
async def test_non_admin_with_engagement_id_member_loads_scoped():
    """Non-admin who pins an engagement they're on: scoped to that
    engagement, mode is irrelevant, never strips."""
    # First DB call is the membership check — return their own user id
    # to simulate a row found.
    db = _FakeDb(["u-1"])
    is_admin, _subq, strip = await apply_stats_scope(
        "eng-1", db, _user(UserRole.OPERATOR)
    )
    assert is_admin is False
    assert strip is False


@pytest.mark.asyncio
async def test_non_admin_with_engagement_id_non_member_403s():
    """The GHSA-ffmc invariant: a non-admin asking for an engagement
    they're not on must always 403 — regardless of toggle mode."""
    from fastapi import HTTPException

    db = _FakeDb([None])  # membership query returns nothing
    with pytest.raises(HTTPException) as exc:
        await apply_stats_scope(
            "eng-x", db, _user(UserRole.OPERATOR)
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_non_admin_engagement_403_even_in_global_mode(monkeypatch):
    """Mode is global — but engagement_id was supplied for one the
    user isn't on. Must STILL 403, because pinning an engagement is
    a stronger signal than the platform-wide toggle."""
    from fastapi import HTTPException

    async def _mode_global(_db):
        return "global"

    monkeypatch.setattr(rbac, "get_stats_scope_mode", _mode_global)
    db = _FakeDb([None])
    with pytest.raises(HTTPException) as exc:
        await apply_stats_scope(
            "eng-x", db, _user(UserRole.OPERATOR)
        )
    assert exc.value.status_code == 403


# ── mode toggle for the no-engagement-id path ───────────────────────


@pytest.mark.asyncio
async def test_non_admin_global_mode_returns_admin_effective_and_strips(monkeypatch):
    """The whole point of the toggle: non-admin + no engagement_id +
    mode=global → scope filter bypassed AND strip flag set so the
    handler anonymises identifiers."""

    async def _mode(_db):
        return "global"

    monkeypatch.setattr(rbac, "get_stats_scope_mode", _mode)
    db = _FakeDb([])
    is_admin, _subq, strip = await apply_stats_scope(
        None, db, _user(UserRole.OPERATOR)
    )
    assert is_admin is True  # bypasses the scope filter
    assert strip is True     # but handler must null out names


@pytest.mark.asyncio
async def test_non_admin_scoped_mode_returns_non_admin_no_strip(monkeypatch):
    """Scoped mode preserves the GHSA-ffmc posture exactly — caller
    sees only their assigned engagements, identifiers stay (their
    own data, no leak risk)."""

    async def _mode(_db):
        return "scoped"

    monkeypatch.setattr(rbac, "get_stats_scope_mode", _mode)
    db = _FakeDb([])
    is_admin, _subq, strip = await apply_stats_scope(
        None, db, _user(UserRole.OPERATOR)
    )
    assert is_admin is False
    assert strip is False


# ── get_stats_scope_mode ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_mode_defaults_to_global_when_unset():
    """No AuthSetting row exists — default to global so a fresh
    install behaves the way the operator intent flag implies."""
    db = _FakeDb([None])
    assert await get_stats_scope_mode(db) == "global"


@pytest.mark.asyncio
async def test_get_mode_returns_scoped_when_set():
    db = _FakeDb(["scoped"])
    assert await get_stats_scope_mode(db) == "scoped"


@pytest.mark.asyncio
async def test_get_mode_normalises_whitespace_and_case():
    """A stray newline or capitalisation shouldn't lock the page out
    by silently falling through to the default."""
    db = _FakeDb(["  GLOBAL  "])
    assert await get_stats_scope_mode(db) == "global"


@pytest.mark.asyncio
async def test_get_mode_falls_back_on_unknown_value():
    """Typo / corrupted value MUST fall back to the default rather
    than fail-closed to nothing — stats should never 500 because
    the setting got mangled."""
    db = _FakeDb(["banana"])
    assert await get_stats_scope_mode(db) == "global"


@pytest.mark.asyncio
async def test_get_mode_falls_back_on_empty_string():
    db = _FakeDb([""])
    assert await get_stats_scope_mode(db) == "global"
