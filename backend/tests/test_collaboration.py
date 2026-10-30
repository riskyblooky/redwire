"""utils/collaboration.py — create_activity_log (+ pure change helpers).

``create_activity_log`` is the audit-trail chokepoint every significant
create/update/delete calls. Contract, pinned here against ``FakeDb`` (no
real DB / WebSocket / automation engine — the three downstream side-effects
are stubbed so we isolate the row-building behaviour):

  1. It constructs exactly one ``ActivityLog`` row with the caller's fields
     and commits it itself (callers must NOT commit).
  2. It fans the event out on the three broadcast channels, passing ``db``
     to the gated ``dashboard:global`` channel.
  3. It emits ``"<resource_type>.<action>"`` on the plugin event bus and
     runs the automation engine with a context dict of the same fields.
  4. Status-change specialised triggers fire only when ``extra_context``
     carries a ``status`` key (and only for the status-bearing resources).
  5. It is non-fatal: a persist failure returns early (rollback, no
     side-effects); a downstream side-effect failure is swallowed.

Also covers the pure change-summary helpers (``build_change_summary`` /
``_fmt``) that ``compute_changes_dict``'s existing test file doesn't.

``compute_changes_dict`` / ``_normalize_for_match`` are already covered in
test_compute_changes_dict.py and deliberately not re-tested here.
"""

from __future__ import annotations

import pytest

import utils.collaboration as collab
from utils.collaboration import create_activity_log, build_change_summary, _fmt
from models.discussion import ActivityLog
from tests.conftest import FakeDb


# ─────────────────────────────────────────────────────────────────────
# Recording stubs for the three downstream side-effects.
# ─────────────────────────────────────────────────────────────────────

class _BroadcastRecorder:
    def __init__(self):
        self.calls = []

    async def __call__(self, resource_type, resource_id, message, db=None):
        self.calls.append(
            {"resource_type": resource_type, "resource_id": resource_id,
             "message": message, "db": db}
        )


@pytest.fixture
def stubbed(monkeypatch):
    """Stub broadcast / event-bus / automation so only row-building runs.

    Returns a namespace of recorders the test can assert against.
    """
    bcast = _BroadcastRecorder()
    monkeypatch.setattr(collab.manager, "broadcast_to_resource", bcast)

    emitted = []

    async def _emit(event_type, data):
        emitted.append({"event_type": event_type, "data": data})

    # create_activity_log does `from utils.event_bus import event_bus` inside,
    # so patch the attribute on the singleton it will resolve.
    import utils.event_bus as eb
    monkeypatch.setattr(eb.event_bus, "emit", _emit)

    rule_calls = []

    async def _evaluate_rules(db, trigger, context):
        rule_calls.append({"trigger": trigger, "context": context})

    import utils.automation_engine as ae
    monkeypatch.setattr(ae, "evaluate_rules", _evaluate_rules)

    from types import SimpleNamespace
    return SimpleNamespace(bcast=bcast, emitted=emitted, rule_calls=rule_calls)


# ═══════════════════════════════════════════════════════════════════
# Row construction + self-commit
# ═══════════════════════════════════════════════════════════════════


async def test_constructs_and_adds_single_activity_log_row(stubbed):
    db = FakeDb()
    await create_activity_log(
        db,
        engagement_id="eng-1",
        user_id="user-1",
        action="created",
        resource_type="finding",
        resource_id="fnd-1",
        resource_name="SQLi in login",
        details="Created finding",
    )
    logs = [o for o in db.added if isinstance(o, ActivityLog)]
    assert len(logs) == 1
    row = logs[0]
    assert row.engagement_id == "eng-1"
    assert row.user_id == "user-1"
    assert row.action == "created"
    assert row.resource_type == "finding"
    assert row.resource_id == "fnd-1"
    assert row.resource_name == "SQLi in login"
    assert row.details == "Created finding"


async def test_commits_itself_caller_need_not(stubbed):
    db = FakeDb()
    await create_activity_log(
        db, "eng-1", "user-1", "updated", "asset", "a-1",
    )
    # One commit for the log row, one for automation side-effects.
    assert db.commit_count >= 1
    assert db.rollback_count == 0


async def test_optional_fields_default_to_none(stubbed):
    db = FakeDb()
    await create_activity_log(db, "eng-1", "user-1", "deleted", "testcase", "tc-1")
    row = [o for o in db.added if isinstance(o, ActivityLog)][0]
    assert row.resource_name is None
    assert row.details is None


# ═══════════════════════════════════════════════════════════════════
# Broadcast channels
# ═══════════════════════════════════════════════════════════════════


async def test_broadcasts_to_three_channels_with_db_on_global(stubbed):
    db = FakeDb()
    await create_activity_log(
        db, "eng-1", "user-1", "created", "finding", "fnd-1",
        resource_name="X", details="d",
    )
    targets = {(c["resource_type"], c["resource_id"]) for c in stubbed.bcast.calls}
    assert ("engagement", "eng-1") in targets
    assert ("dashboard", "global") in targets
    assert ("dashboard", "eng-1") in targets

    # The gated cross-engagement channel must receive the db session so the
    # per-recipient ENGAGEMENT_VIEW filter can run (GHSA-pqj4-49q4-rw4f).
    global_call = next(
        c for c in stubbed.bcast.calls
        if c["resource_type"] == "dashboard" and c["resource_id"] == "global"
    )
    assert global_call["db"] is db
    # And the payload carries the engagement_id the filter keys on.
    assert global_call["message"]["engagement_id"] == "eng-1"
    assert global_call["message"]["type"] == "activity_log"


# ═══════════════════════════════════════════════════════════════════
# Event bus + automation engine
# ═══════════════════════════════════════════════════════════════════


async def test_emits_event_bus_name(stubbed):
    db = FakeDb()
    await create_activity_log(db, "eng-1", "user-1", "resolved", "finding", "fnd-1")
    assert any(e["event_type"] == "finding.resolved" for e in stubbed.emitted)


async def test_runs_automation_engine_with_context(stubbed):
    db = FakeDb()
    await create_activity_log(
        db, "eng-1", "user-1", "created", "finding", "fnd-1",
        resource_name="X",
    )
    generic = [c for c in stubbed.rule_calls if c["trigger"] == "created"]
    assert len(generic) == 1
    ctx = generic[0]["context"]
    assert ctx["action"] == "created"
    assert ctx["resource_type"] == "finding"
    assert ctx["resource_id"] == "fnd-1"
    assert ctx["engagement_id"] == "eng-1"
    assert ctx["user_id"] == "user-1"


async def test_extra_context_merged_into_automation_context(stubbed):
    db = FakeDb()
    await create_activity_log(
        db, "eng-1", "user-1", "updated", "finding", "fnd-1",
        extra_context={"severity": "critical", "changes": {"x": 1}},
    )
    ctx = next(c for c in stubbed.rule_calls if c["trigger"] == "updated")["context"]
    assert ctx["severity"] == "critical"
    assert ctx["changes"] == {"x": 1}


# ── status-change specialised triggers ───────────────────────────────


async def test_status_change_fires_finding_status_trigger(stubbed):
    db = FakeDb()
    await create_activity_log(
        db, "eng-1", "user-1", "updated", "finding", "fnd-1",
        extra_context={"status": "RESOLVED",
                       "changes": {"status": {"old": "OPEN", "new": "RESOLVED"}}},
    )
    triggers = {c["trigger"] for c in stubbed.rule_calls}
    assert "updated" in triggers
    assert "finding_status_changed" in triggers


async def test_status_present_without_transition_does_not_fire(stubbed):
    # Creates and non-status edits carry the current status in extra_context;
    # only a recorded status change may fire *_status_changed (2f7f906).
    db = FakeDb()
    await create_activity_log(
        db, "eng-1", "user-1", "updated", "finding", "fnd-1",
        extra_context={"status": "OPEN", "changes": {"title": {"old": "a", "new": "b"}}},
    )
    assert {c["trigger"] for c in stubbed.rule_calls} == {"updated"}


@pytest.mark.parametrize(
    "resource_type,expected",
    [
        ("finding", "finding_status_changed"),
        ("engagement", "engagement_status_changed"),
        ("cleanup_artifact", "cleanup_status_changed"),
    ],
)
async def test_status_trigger_matches_resource_type(stubbed, resource_type, expected):
    db = FakeDb()
    await create_activity_log(
        db, "eng-1", "user-1", "updated", resource_type, "r-1",
        extra_context={"status": "X", "changes": {"status": {"old": "W", "new": "X"}}},
    )
    assert expected in {c["trigger"] for c in stubbed.rule_calls}


async def test_no_status_trigger_without_status_key(stubbed):
    db = FakeDb()
    await create_activity_log(
        db, "eng-1", "user-1", "updated", "finding", "fnd-1",
        extra_context={"severity": "high"},
    )
    triggers = {c["trigger"] for c in stubbed.rule_calls}
    assert triggers == {"updated"}


async def test_no_status_trigger_for_unlisted_resource(stubbed):
    db = FakeDb()
    await create_activity_log(
        db, "eng-1", "user-1", "updated", "asset", "a-1",
        extra_context={"status": "X"},
    )
    # asset isn't a status-trigger resource → only the generic trigger fires.
    assert {c["trigger"] for c in stubbed.rule_calls} == {"updated"}


# ═══════════════════════════════════════════════════════════════════
# Non-fatal failure paths
# ═══════════════════════════════════════════════════════════════════


class _PersistFailDb(FakeDb):
    """Commit blows up on the FIRST call (the log-row persist)."""

    async def commit(self):
        self.commit_count += 1
        raise RuntimeError("db down")


async def test_persist_failure_returns_early_and_rolls_back(stubbed):
    db = _PersistFailDb()
    result = await create_activity_log(
        db, "eng-1", "user-1", "created", "finding", "fnd-1",
    )
    assert result is None
    assert db.rollback_count == 1
    # Side-effects must NOT run when the row couldn't even be persisted.
    assert stubbed.bcast.calls == []
    assert stubbed.emitted == []
    assert stubbed.rule_calls == []


async def test_broadcast_failure_is_non_fatal(stubbed, monkeypatch):
    async def _boom(*a, **k):
        raise RuntimeError("socket exploded")

    monkeypatch.setattr(collab.manager, "broadcast_to_resource", _boom)
    db = FakeDb()
    # Should not raise even though every broadcast attempt throws.
    await create_activity_log(db, "eng-1", "user-1", "created", "finding", "fnd-1")
    # The log row still persisted before the broadcast attempt.
    assert any(isinstance(o, ActivityLog) for o in db.added)


async def test_automation_failure_is_non_fatal_and_rolls_back(stubbed, monkeypatch):
    async def _boom(db, trigger, context):
        raise RuntimeError("rule engine exploded")

    import utils.automation_engine as ae
    monkeypatch.setattr(ae, "evaluate_rules", _boom)
    db = FakeDb()
    await create_activity_log(db, "eng-1", "user-1", "created", "finding", "fnd-1")
    # Log row persisted (first commit) and the automation error triggers a rollback.
    assert any(isinstance(o, ActivityLog) for o in db.added)
    assert db.rollback_count == 1


# ═══════════════════════════════════════════════════════════════════
# Pure change-summary helpers (build_change_summary / _fmt)
# ═══════════════════════════════════════════════════════════════════


def test_fmt_formats_none_bool_and_long_string():
    assert _fmt(None) == "none"
    assert _fmt(True) == "true"
    assert _fmt(False) == "false"
    long = "x" * 100
    out = _fmt(long)
    assert out.endswith("...'") and out.startswith("'") and len(out) < len(long)
    assert _fmt("short") == "short"


def test_build_change_summary_short_field():
    old = type("O", (), {"status": "planning", "name": "Old"})()
    out = build_change_summary(old, {"status": "active"})
    assert "status: planning → active" in out


def test_build_change_summary_long_field_omits_values():
    old = type("O", (), {"description": "before"})()
    out = build_change_summary(old, {"description": "a totally new and longer body"})
    # Long-text fields only note that they changed, not the values.
    assert "description" in out
    assert "before" not in out and "longer body" not in out


def test_build_change_summary_skips_unchanged():
    old = type("O", (), {"status": "active", "name": "Same"})()
    out = build_change_summary(old, {"status": "active", "name": "Same"})
    assert "no field changes" in out


def test_build_change_summary_redacts_vault_fields():
    from utils.vault_crypto import ENCRYPTED_FIELDS
    if not ENCRYPTED_FIELDS:
        pytest.skip("no encrypted fields configured")
    field = sorted(ENCRYPTED_FIELDS)[0]
    old = type("O", (), {field: "OLD-CIPHERTEXT"})()
    out = build_change_summary(old, {field: "new-plaintext-secret"})
    assert "new-plaintext-secret" not in out
    assert "OLD-CIPHERTEXT" not in out
    assert "(changed)" in out
