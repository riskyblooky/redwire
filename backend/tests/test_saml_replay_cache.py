"""``claim_saml_assertion`` regressions (GHSA-68hx-hggg-vrr2 follow-up).

Single-use SAML assertions via atomic SET NX against Redis. Replay of
the same assertion ID inside its NotOnOrAfter window must be refused;
Redis-down must fail closed; missing or already-expired assertions
must be refused.

These tests stub the Redis client at the ``auth.saml_replay._get_redis``
import site so we can exercise every branch without standing up Redis
in the test environment.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from auth import saml_replay
from auth.saml_replay import claim_saml_assertion, _KEY_PREFIX, _MIN_TTL_SECONDS


def _future(minutes: int = 5) -> datetime:
    return datetime.utcnow() + timedelta(minutes=minutes)


def _past(minutes: int = 5) -> datetime:
    return datetime.utcnow() - timedelta(minutes=minutes)


class _FakeRedis:
    """In-memory stand-in for the subset of redis-py we exercise here."""

    def __init__(self):
        self.store: dict[str, str] = {}
        self.calls: list[dict] = []

    def set(self, key, value, nx=False, ex=None):
        self.calls.append({"key": key, "nx": nx, "ex": ex})
        if nx and key in self.store:
            return None  # NX collision — replay
        self.store[key] = value
        return True


# ── happy path ────────────────────────────────────────────────────────


def test_first_claim_returns_true(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(saml_replay, "_get_redis", lambda: fake)

    assert claim_saml_assertion("_assertion-001", _future()) is True
    # Key was written with the expected prefix.
    assert f"{_KEY_PREFIX}_assertion-001" in fake.store


def test_ttl_matches_not_on_or_after(monkeypatch):
    """TTL should round to roughly NotOnOrAfter - now, in seconds."""
    fake = _FakeRedis()
    monkeypatch.setattr(saml_replay, "_get_redis", lambda: fake)

    claim_saml_assertion("_assertion-002", _future(minutes=10))
    ex = fake.calls[0]["ex"]
    # 10 minutes ± a few seconds for test overhead.
    assert 590 <= ex <= 610


# ── replay detection ─────────────────────────────────────────────────


def test_second_claim_for_same_id_returns_false(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(saml_replay, "_get_redis", lambda: fake)
    deadline = _future()

    assert claim_saml_assertion("_assertion-003", deadline) is True
    # Replay of the same ID within the window.
    assert claim_saml_assertion("_assertion-003", deadline) is False


# ── fail-closed paths ───────────────────────────────────────────────


def test_redis_unavailable_returns_false(monkeypatch):
    """Per the same fail-closed contract as is_token_blacklisted: when
    we can't verify uniqueness, refuse the assertion entirely."""
    monkeypatch.setattr(saml_replay, "_get_redis", lambda: None)

    assert claim_saml_assertion("_assertion-004", _future()) is False


def test_redis_call_exception_returns_false(monkeypatch):
    """A Redis op that throws mid-call (network blip, cluster issue)
    must surface as a refusal, not a silent accept."""
    fake = MagicMock()
    fake.set.side_effect = RuntimeError("redis down")
    monkeypatch.setattr(saml_replay, "_get_redis", lambda: fake)

    assert claim_saml_assertion("_assertion-005", _future()) is False


# ── input validation ────────────────────────────────────────────────


@pytest.mark.parametrize("bad_id", [None, "", 0, 12345, b"_assertion"])
def test_missing_or_non_string_assertion_id_returns_false(monkeypatch, bad_id):
    """An assertion without an ID — or with one that isn't a string —
    isn't replay-detectable. Refuse rather than degrade silently."""
    fake = _FakeRedis()
    monkeypatch.setattr(saml_replay, "_get_redis", lambda: fake)

    assert claim_saml_assertion(bad_id, _future()) is False
    # And we didn't touch Redis with garbage input.
    assert fake.calls == []


def test_missing_not_on_or_after_returns_false(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(saml_replay, "_get_redis", lambda: fake)

    assert claim_saml_assertion("_assertion-006", None) is False


def test_already_past_not_on_or_after_returns_false(monkeypatch):
    """The python3-saml validator should have rejected this upstream;
    a defensive floor here surfaces an out-of-window assertion as a
    replay-class failure rather than letting Redis ex=0 raise."""
    fake = _FakeRedis()
    monkeypatch.setattr(saml_replay, "_get_redis", lambda: fake)

    assert claim_saml_assertion("_assertion-007", _past()) is False
    assert fake.calls == []  # never reached Redis


def test_ttl_below_minimum_floor_returns_false(monkeypatch):
    """An assertion whose window is shorter than the floor would write
    a TTL that's too short to outlive the window itself — refuse so a
    future replay would land on a fresh slot instead."""
    fake = _FakeRedis()
    monkeypatch.setattr(saml_replay, "_get_redis", lambda: fake)
    # Floor is 60s; pick something safely below.
    too_close = datetime.utcnow() + timedelta(seconds=_MIN_TTL_SECONDS - 10)

    assert claim_saml_assertion("_assertion-008", too_close) is False


# ── timezone handling ──────────────────────────────────────────────


def test_timezone_aware_not_on_or_after_is_handled(monkeypatch):
    """python3-saml returns NotOnOrAfter as a naive datetime today, but
    a future toolkit update or a different SAML lib could deliver
    tz-aware values. Coerce both shapes."""
    fake = _FakeRedis()
    monkeypatch.setattr(saml_replay, "_get_redis", lambda: fake)
    aware_future = datetime.now(tz=timezone.utc) + timedelta(minutes=5)

    assert claim_saml_assertion("_assertion-009", aware_future) is True
