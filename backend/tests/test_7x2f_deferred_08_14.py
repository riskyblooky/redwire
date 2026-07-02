"""GHSA-7x2f-ff7r-h388 — deferred items #8 and #14 shipped.

#8  (CWE-20)   Thread.resource_type + ActivityLog.resource_type on
    engagement import now enum-coerced against the ResourceType
    values. Unknown values fall back to ENGAGEMENT + log.

#14 (CWE-696)  Runbook apply now commits the created test cases
    BEFORE the activity-log side effect, and the activity-log call
    is wrapped in its own try/except so a log failure can't roll
    back the applied test cases.
"""

from __future__ import annotations

import os

import pytest
from cryptography.fernet import Fernet

os.environ.setdefault("TOTP_ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ.setdefault("VAULT_ENCRYPTION_KEY", Fernet.generate_key().decode())


# ── #8: resource_type enum coercion ──────────────────────────────────


class TestResourceTypeEnumCoerce:
    """Static-shape regression: the coercion path must remain in the
    import handler. A future refactor that drops `_valid_resource_types`
    or the coerce loop should trip this test."""

    def test_valid_resource_types_computed_from_enum(self):
        # The set the handler compares against must derive from the
        # ResourceType enum — otherwise a new enum value added to the
        # model would silently drop through the coerce path even
        # though it's now legit.
        from models.discussion import ResourceType
        expected = {v.value for v in ResourceType}
        # Sanity: the enum has all 12 values the model documents.
        assert "engagement" in expected
        assert "finding" in expected
        assert "asset" in expected
        assert "testcase" in expected
        assert "evidence" in expected
        assert "comment" in expected
        assert "vault" in expected
        assert "thread" in expected
        assert "template" in expected
        assert "note" in expected
        assert "cleanup_artifact" in expected
        assert "finding_remediation" in expected

    def test_import_handler_has_coerce_guard(self):
        # The Thread + ActivityLog imports MUST both build against the
        # same enum-derived set. Search the transfer module.
        src = open("/app/routers/engagements_transfer.py").read()
        # The coerce set must be built from the enum, not hardcoded.
        assert "_valid_resource_types = {v.value for v in ResourceType}" in src
        # Both Thread and ActivityLog import blocks must use it — the
        # warning message is the load-bearing signal.
        assert 'unknown resource_type=' in src
        # Two callsites (threads + activity_logs)
        assert src.count('_valid_resource_types') >= 3  # 1 def + 2 checks

    def test_coerce_falls_back_to_engagement(self):
        # Pin the fallback shape so a future edit doesn't accidentally
        # switch to raise-on-unknown, which would refuse the whole
        # archive on any legacy or third-party-provider row.
        src = open("/app/routers/engagements_transfer.py").read()
        assert "ResourceType.ENGAGEMENT.value" in src


# ── #14: runbook-apply commit ordering ───────────────────────────────


class TestRunbookApplyCommitOrdering:
    """Static-shape regression: the explicit `await db.commit()` must
    appear BEFORE `await create_activity_log(` inside the apply
    handler, and the log call must be wrapped in try/except so it
    can't propagate an exception."""

    def _apply_handler_slice(self) -> str:
        src = open("/app/routers/runbooks.py").read()
        idx = src.find("async def apply_runbook_to_engagement")
        assert idx != -1, "apply_runbook_to_engagement not found"
        rest = src[idx:]
        # Slice to the next top-level def or router decorator.
        end = rest.find("\n@router.")
        return rest[:end] if end != -1 else rest

    def test_commit_before_activity_log(self):
        block = self._apply_handler_slice()
        commit_idx = block.find("await db.commit()")
        log_idx = block.find("await create_activity_log(")
        assert commit_idx != -1
        assert log_idx != -1
        assert commit_idx < log_idx, "commit must precede activity_log call"

    def test_activity_log_wrapped_in_try_except(self):
        block = self._apply_handler_slice()
        log_idx = block.find("await create_activity_log(")
        # Look backwards from the log call for the enclosing try.
        preceding = block[:log_idx]
        assert preceding.rstrip().endswith("try:"), (
            "create_activity_log call must be inside a try/except"
        )
        # And there must be an except after it in the block.
        assert "except Exception" in block[log_idx:]

    def test_no_regression_to_single_commit_shape(self):
        block = self._apply_handler_slice()
        # The old shape had NO explicit commit in the handler — the
        # test-case creations only landed via create_activity_log's
        # side effect. Pin that the string "await db.commit()"
        # appears at least once so the pre-fix state can't come back.
        assert "await db.commit()" in block
