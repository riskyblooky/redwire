"""``/auth/register`` refuses the bootstrap admin username and well-known
aliases (GHSA-28f5-4wcg-9pwv follow-up). Belt-and-suspenders so the
seeder gate added in that advisory isn't load-bearing on its own.

The actual register endpoint pulls in a chain of imports (rate limiter,
db session, auth settings) that make a full HTTP test heavy for the
shape we're checking. Instead we pin the helper directly: it's the unit
of behavior the route consults, and any change to its output is what
would regress the gate.
"""

from __future__ import annotations

import pytest

from routers.auth import _reserved_usernames


def test_includes_well_known_admin_aliases(monkeypatch):
    monkeypatch.delenv("ADMIN_USERNAME", raising=False)
    reserved = _reserved_usernames()
    for name in ("admin", "administrator", "root", "system", "redwire"):
        assert name in reserved, f"{name!r} not in reserved set"


def test_includes_configured_admin_username(monkeypatch):
    monkeypatch.setenv("ADMIN_USERNAME", "rwadmin")
    assert "rwadmin" in _reserved_usernames()


def test_case_folds_configured_admin_username(monkeypatch):
    """UserCreate runs NFKC + casefold via the username validator, so the
    reserved-set check works against the already-folded value. A
    deployment that sets ADMIN_USERNAME=RWAdmin should still reject
    `rwadmin` at register time."""
    monkeypatch.setenv("ADMIN_USERNAME", "RWAdmin")
    assert "rwadmin" in _reserved_usernames()


def test_empty_env_var_is_ignored(monkeypatch):
    """An unset / blank ADMIN_USERNAME must not add the empty string to
    the reserved set (otherwise every username would fall through the
    pre-validator and 400)."""
    monkeypatch.setenv("ADMIN_USERNAME", "   ")
    reserved = _reserved_usernames()
    assert "" not in reserved
    assert "admin" in reserved  # base set still present


def test_rotated_env_var_picks_up_on_next_call(monkeypatch):
    """Per-call read of the env var: a deployment that rotates the value
    doesn't need a process restart."""
    monkeypatch.setenv("ADMIN_USERNAME", "old-admin")
    assert "old-admin" in _reserved_usernames()
    monkeypatch.setenv("ADMIN_USERNAME", "new-admin")
    reserved = _reserved_usernames()
    assert "new-admin" in reserved
    assert "old-admin" not in reserved
