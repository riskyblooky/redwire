"""``should_log_vault_access`` regressions (GHSA-fp69-w2mg-4pqp follow-up).

Per-(user, vault-item) reveal-log dedup window. First reveal of a given
pair inside the 5-minute window writes an audit row; subsequent calls
return False so the caller skips the log. Fail-open contract: Redis
down means we log without dedup rather than silently drop the audit
trail.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from utils import vault_access_log
from utils.vault_access_log import (
    _DEDUP_WINDOW_SECONDS,
    _KEY_PREFIX,
    should_log_vault_access,
)


class _FakeRedis:
    def __init__(self):
        self.store: dict[str, str] = {}
        self.calls: list[dict] = []

    def set(self, key, value, nx=False, ex=None):
        self.calls.append({"key": key, "nx": nx, "ex": ex})
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True


def test_first_call_returns_true(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(vault_access_log, "_get_redis", lambda: fake)

    assert should_log_vault_access("user-1", "item-1") is True
    assert fake.calls == [
        {"key": f"{_KEY_PREFIX}user-1:item-1", "nx": True, "ex": _DEDUP_WINDOW_SECONDS},
    ]


def test_second_call_within_window_returns_false(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(vault_access_log, "_get_redis", lambda: fake)

    assert should_log_vault_access("user-1", "item-1") is True
    assert should_log_vault_access("user-1", "item-1") is False


def test_different_user_same_item_logs_separately(monkeypatch):
    """Dedup is per (user, item), not per item. Two separate operators
    pulling the same credential each get their own audit row."""
    fake = _FakeRedis()
    monkeypatch.setattr(vault_access_log, "_get_redis", lambda: fake)

    assert should_log_vault_access("user-1", "item-1") is True
    assert should_log_vault_access("user-2", "item-1") is True


def test_same_user_different_items_logs_separately(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(vault_access_log, "_get_redis", lambda: fake)

    assert should_log_vault_access("user-1", "item-1") is True
    assert should_log_vault_access("user-1", "item-2") is True


def test_redis_unavailable_fails_open(monkeypatch):
    """Opposite of the SAML replay cache fail-closed contract — here
    we'd rather over-log than under-log when we can't dedup."""
    monkeypatch.setattr(vault_access_log, "_get_redis", lambda: None)

    assert should_log_vault_access("user-1", "item-1") is True


def test_redis_call_exception_fails_open(monkeypatch):
    fake = MagicMock()
    fake.set.side_effect = RuntimeError("redis cluster blip")
    monkeypatch.setattr(vault_access_log, "_get_redis", lambda: fake)

    assert should_log_vault_access("user-1", "item-1") is True


@pytest.mark.parametrize("bad_user, bad_item", [
    ("", "item-1"),
    ("user-1", ""),
    (None, "item-1"),
    ("user-1", None),
    ("", ""),
])
def test_missing_user_or_item_defensively_logs(monkeypatch, bad_user, bad_item):
    """Missing either half makes dedup impossible — log defensively
    rather than silently no-op the audit trail."""
    fake = _FakeRedis()
    monkeypatch.setattr(vault_access_log, "_get_redis", lambda: fake)

    assert should_log_vault_access(bad_user, bad_item) is True
    # Didn't touch Redis with empty/None inputs.
    assert fake.calls == []
