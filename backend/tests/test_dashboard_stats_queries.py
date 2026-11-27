"""/analytics/dashboard-stats: exact numbers on seeded data, and a bounded
number of SQL statements (it used to run ~25 one after another and load
every finding and test case of the caller's engagements to count them)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import event

from tests.test_authz_boundaries import _assign, _make_engagement, _make_engagement_role


def _u():
    return str(uuid.uuid4())


@pytest.fixture
def count_statements(db_session):
    engine = db_session.bind.sync_engine if hasattr(db_session.bind, "sync_engine") else db_session.bind.engine.sync_engine
    seen: list[str] = []

    def _on(conn, cursor, statement, *a):
        if not statement.lstrip().upper().startswith(("SAVEPOINT", "RELEASE", "ROLLBACK")):
            seen.append(statement)
    event.listen(engine, "before_cursor_execute", _on)
    yield seen
    event.remove(engine, "before_cursor_execute", _on)


async def _seed(db, me, other):
    from models.cleanup_artifact import CleanupArtifact, CleanupArtifactStatus
    from models.engagement import EngagementStatus
    from models.finding import Finding, FindingStatus, Severity
    from models.notification import Notification
    from models.testcase import TestCase
    role = await _make_engagement_role(db, ["finding_view"])
    eng = await _make_engagement(db, status=EngagementStatus.IN_PROGRESS)
    eng2 = await _make_engagement(db, status=EngagementStatus.PLANNING,
                                  start_date=datetime.utcnow() + timedelta(days=3))
    eng3 = await _make_engagement(db, status=EngagementStatus.COMPLETED)
    for e in (eng, eng2, eng3):
        await _assign(db, me, e, role)
    await _assign(db, other, eng, role)
    old = datetime.utcnow() - timedelta(days=70)
    F = [  # severity, status, created_by, old?
        (Severity.CRITICAL, FindingStatus.OPEN, me, False),
        (Severity.CRITICAL, FindingStatus.VERIFIED, other, False),
        (Severity.HIGH, FindingStatus.IN_REVIEW, me, True),
        (Severity.HIGH, FindingStatus.CLOSED, other, True),
        (Severity.MEDIUM, FindingStatus.OPEN, other, False),
        (Severity.LOW, FindingStatus.REMEDIATED, me, False),
        (Severity.INFO, FindingStatus.OPEN, me, False),
    ]
    for sev, st, who, is_old in F:
        f = Finding(id=_u(), engagement_id=eng.id, title=f"{sev.value}-{st.value}", description="d",
                    severity=sev, status=st, created_by=who.id)
        if is_old:
            f.created_at = f.updated_at = old
        db.add(f)
    db.add(Finding(id=_u(), engagement_id=eng2.id, title="e2", description="d",
                   severity=Severity.HIGH, status=FindingStatus.OPEN, created_by=me.id))
    for executed in (False, False, True):
        db.add(TestCase(id=_u(), engagement_id=eng.id, title="t", category="Recon", description="d",
                        is_executed=executed, created_by=me.id))
    db.add(TestCase(id=_u(), engagement_id=eng3.id, title="t3", category="Recon", description="d",
                    is_executed=False, created_by=me.id))
    for st in (CleanupArtifactStatus.PENDING, CleanupArtifactStatus.PARTIALLY_CLEANED,
               CleanupArtifactStatus.CLEANED):
        db.add(CleanupArtifact(id=_u(), engagement_id=eng.id, title="c", artifact_type="file", status=st))
    db.add(Notification(id=_u(), user_id=me.id, event_type="x", title="n", is_read=False))
    db.add(Notification(id=_u(), user_id=me.id, event_type="x", title="n", is_read=True))
    await db.flush()
    return eng, eng2, eng3


async def _scoped(db):
    return "scoped"


async def test_dashboard_stats_numbers(client, db_session, make_user, authenticate_as, count_statements,
                                       monkeypatch):
    import auth.rbac
    monkeypatch.setattr(auth.rbac, "get_stats_scope_mode", _scoped)
    me = await make_user(role="operator")
    other = await make_user(role="operator")
    eng, eng2, _eng3 = await _seed(db_session, me, other)
    authenticate_as(me)
    count_statements.clear()
    r = await client.get("/analytics/dashboard-stats")
    assert r.status_code == 200, r.text
    n_statements = len(count_statements)
    d = r.json()

    assert d["active_engagements"] == {"total": 2, "in_progress": 1, "planning": 1, "reporting": 0}
    f = d["findings"]
    assert f["total"] == 8 and f["critical"] == 2
    # VERIFIED + REMEDIATED this month; the CLOSED one is 70 days old.
    assert f["resolved_this_month"] == 2
    sev = {s["severity"]: s["count"] for s in f["severity_breakdown"]}
    assert sev == {"Critical": 2, "High": 3, "Medium": 1, "Low": 1, "Info": 1}
    assert [s["severity"] for s in f["severity_breakdown"]] == ["Critical", "High", "Medium", "Low", "Info"]
    st = {s["status"]: s["count"] for s in f["status_breakdown"]}
    assert st["OPEN"] == 4 and st["VERIFIED"] == 1 and st["CLOSED"] == 1 and st["IN_REVIEW"] == 1
    assert st["REMEDIATED"] == 1 and sum(st.values()) == 8

    top = d["top_findings"]
    assert [t["title"] for t in top][:1] == ["CRITICAL-OPEN"]
    assert {t["title"] for t in top} == {"CRITICAL-OPEN", "HIGH-IN_REVIEW", "e2"}

    assert d["pending_cleanup"] == 2
    mine = {e["id"]: e for e in d["my_engagements"]}
    assert set(mine) == {eng.id, eng2.id}
    assert mine[eng.id]["finding_count"] == 7 and mine[eng.id]["testcase_count"] == 3
    assert mine[eng2.id]["finding_count"] == 1 and mine[eng2.id]["testcase_count"] == 0
    assert mine[eng.id]["user_role"] and mine[eng.id]["user_role"].startswith("role_")
    assert [e["id"] for e in d["upcoming_engagements"]] == [eng2.id]

    p = d["personal_stats"]
    assert p == {
        "my_active_engagements": 2,
        "my_open_findings": 4,          # CRITICAL-OPEN, HIGH-IN_REVIEW, INFO-OPEN, e2
        "my_pending_tests": 2,          # eng3 is COMPLETED, so its unexecuted test doesn't count
        "my_findings_this_month": 4,    # HIGH-IN_REVIEW is 70 days old
        "my_pending_cleanup": 2,
        "my_unread_notifications": 1,
    }
    assert n_statements <= 12, f"{n_statements} statements"


async def test_global_mode_strips_identifiers(client, db_session, make_user, authenticate_as):
    me = await make_user(role="operator")
    other = await make_user(role="operator")
    await _seed(db_session, me, other)
    authenticate_as(me)
    d = (await client.get("/analytics/dashboard-stats")).json()
    assert d["top_findings"] and all(t["title"] is None and t["engagement_name"] is None
                                     for t in d["top_findings"])
    assert all(e["name"] is None for e in d["upcoming_engagements"])
    assert all(a["user"] is None for a in d["recent_activity"])
