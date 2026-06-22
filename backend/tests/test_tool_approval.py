"""Regressions for the per-call MCP write-tool approval gate.

The chat router's tool-use loop calls ``wait_for_approval`` from a
background thread before executing a write tool. ``record_decision``
publishes the user's UI click. The gate is fail-closed — any path
that can't return APPROVE (Redis down, BLPOP error, unknown payload,
timeout) must return DENY/TIMEOUT so a write isn't silently
performed. These tests pin every fail-closed branch.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from utils import tool_approval
from utils.tool_approval import (
    ApprovalDecision,
    parse_decision,
    record_decision,
    wait_for_approval,
)


# ── parse_decision ──────────────────────────────────────────────────


@pytest.mark.parametrize("raw, expected", [
    ("approve", ApprovalDecision.APPROVE),
    ("deny", ApprovalDecision.DENY),
    ("APPROVE", ApprovalDecision.APPROVE),
    ("  Deny  ", ApprovalDecision.DENY),
    (b"approve", ApprovalDecision.APPROVE),
    (b"deny", ApprovalDecision.DENY),
])
def test_parse_decision_accepts_recognised(raw, expected):
    assert parse_decision(raw) == expected


@pytest.mark.parametrize("raw", [
    None,
    "",
    "yes",
    "no",
    "maybe",
    123,
    object(),
    b"\xff\xfe",  # non-utf8 bytes
])
def test_parse_decision_returns_none_for_unrecognised(raw):
    """Anything not "approve"/"deny" returns None — callers treat
    that as DENY (fail-closed)."""
    assert parse_decision(raw) is None


# ── wait_for_approval ────────────────────────────────────────────────


def test_wait_returns_approve_on_blpop_approve(monkeypatch):
    fake = MagicMock()
    fake.blpop.return_value = ("redwire:tool_approval:cid-1", b"approve")
    monkeypatch.setattr(tool_approval, "_get_redis", lambda: fake)

    assert wait_for_approval("cid-1", timeout_seconds=1) == ApprovalDecision.APPROVE
    fake.blpop.assert_called_once_with("redwire:tool_approval:cid-1", timeout=1)


def test_wait_returns_deny_on_blpop_deny(monkeypatch):
    fake = MagicMock()
    fake.blpop.return_value = ("redwire:tool_approval:cid-2", b"deny")
    monkeypatch.setattr(tool_approval, "_get_redis", lambda: fake)

    assert wait_for_approval("cid-2", timeout_seconds=1) == ApprovalDecision.DENY


def test_wait_returns_timeout_on_blpop_timeout(monkeypatch):
    """BLPOP returning None means the timeout elapsed with no LPUSH —
    the user never clicked. Treat as TIMEOUT (still fail-closed)."""
    fake = MagicMock()
    fake.blpop.return_value = None
    monkeypatch.setattr(tool_approval, "_get_redis", lambda: fake)

    assert wait_for_approval("cid-3", timeout_seconds=1) == ApprovalDecision.TIMEOUT


def test_wait_returns_deny_when_redis_unavailable(monkeypatch):
    """No Redis ⇒ no approval substrate ⇒ deny. NEVER auto-approve
    because the gate substrate is down."""
    monkeypatch.setattr(tool_approval, "_get_redis", lambda: None)

    assert wait_for_approval("cid-4", timeout_seconds=1) == ApprovalDecision.DENY


def test_wait_returns_deny_when_blpop_raises(monkeypatch):
    fake = MagicMock()
    fake.blpop.side_effect = RuntimeError("redis cluster blip")
    monkeypatch.setattr(tool_approval, "_get_redis", lambda: fake)

    assert wait_for_approval("cid-5", timeout_seconds=1) == ApprovalDecision.DENY


def test_wait_returns_deny_on_unrecognised_blpop_payload(monkeypatch):
    """An LPUSH of a non-approve/deny string shouldn't accidentally
    pass through as APPROVE — the payload parser returns None and the
    wait coerces to DENY."""
    fake = MagicMock()
    fake.blpop.return_value = ("key", b"yes please")
    monkeypatch.setattr(tool_approval, "_get_redis", lambda: fake)

    assert wait_for_approval("cid-6", timeout_seconds=1) == ApprovalDecision.DENY


@pytest.mark.parametrize("bad", [None, "", 123, object()])
def test_wait_returns_deny_on_invalid_call_id(monkeypatch, bad):
    """Defensive — invalid call_id should never trigger a Redis call,
    and must default to DENY."""
    sentinel = MagicMock()
    monkeypatch.setattr(tool_approval, "_get_redis", lambda: sentinel)

    assert wait_for_approval(bad, timeout_seconds=1) == ApprovalDecision.DENY
    sentinel.blpop.assert_not_called()


# ── record_decision ──────────────────────────────────────────────────


def test_record_decision_lpushes_and_expires(monkeypatch):
    fake = MagicMock()
    monkeypatch.setattr(tool_approval, "_get_redis", lambda: fake)

    assert record_decision("cid-1", ApprovalDecision.APPROVE) is True
    fake.lpush.assert_called_once_with("redwire:tool_approval:cid-1", "approve")
    fake.expire.assert_called_once_with(
        "redwire:tool_approval:cid-1", tool_approval._WAIT_TIMEOUT_SECONDS,
    )


def test_record_decision_returns_false_when_redis_unavailable(monkeypatch):
    """The HTTP endpoint surfaces this as 503 so the user sees a
    clear "approval substrate down" error rather than waiting 5
    minutes for the BLPOP timeout."""
    monkeypatch.setattr(tool_approval, "_get_redis", lambda: None)

    assert record_decision("cid-1", ApprovalDecision.APPROVE) is False


def test_record_decision_returns_false_when_lpush_raises(monkeypatch):
    fake = MagicMock()
    fake.lpush.side_effect = RuntimeError("redis disk full")
    monkeypatch.setattr(tool_approval, "_get_redis", lambda: fake)

    assert record_decision("cid-1", ApprovalDecision.APPROVE) is False


@pytest.mark.parametrize("bad", [None, "", 123, object()])
def test_record_decision_rejects_invalid_call_id(monkeypatch, bad):
    sentinel = MagicMock()
    monkeypatch.setattr(tool_approval, "_get_redis", lambda: sentinel)

    assert record_decision(bad, ApprovalDecision.APPROVE) is False
    sentinel.lpush.assert_not_called()
