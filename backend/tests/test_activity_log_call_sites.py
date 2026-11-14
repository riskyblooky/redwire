"""create_activity_log is called after the change it records is committed,
and never commits or rolls back a caller's pending work."""

from __future__ import annotations

import ast
import uuid
from pathlib import Path

from sqlalchemy import select

_WRITES = {"add", "add_all", "delete", "flush", "merge"}
_SQL_WRITES = {"delete", "update", "insert", "sa_delete", "_sa_delete", "sa_update", "_sa_update", "_delete"}


def _is_db_write(call: ast.Call) -> bool:
    f = call.func
    if not (isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "db"):
        return False
    if f.attr in _WRITES:
        return True
    if f.attr == "execute" and call.args and isinstance(call.args[0], ast.Call):
        inner = call.args[0]
        while isinstance(inner.func, ast.Attribute) and isinstance(inner.func.value, ast.Call):
            inner = inner.func.value  # delete(X).where(...) -> delete(X)
        name = getattr(inner.func, "id", getattr(inner.func, "attr", None))
        return name in _SQL_WRITES
    return False


def test_no_call_site_logs_before_committing_its_writes():
    """A write between the function's last commit and the log call would be
    committed by the log (before), or left uncommitted (now). Either way the
    log belongs after the commit."""
    offenders = []
    files = list(Path("routers").glob("*.py")) + list(Path("utils").glob("*.py")) + list(Path("auth").glob("*.py"))
    for path in files:
        tree = ast.parse(path.read_text())
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            calls = sorted((n for n in ast.walk(fn) if isinstance(n, ast.Call)), key=lambda n: n.lineno)
            for log in (c for c in calls if getattr(c.func, "id", getattr(c.func, "attr", None)) == "create_activity_log"):
                commits = [c.lineno for c in calls if getattr(c.func, "attr", None) == "commit" and c.lineno < log.lineno]
                since = max(commits) if commits else fn.lineno
                writes = [c.lineno for c in calls if since < c.lineno < log.lineno and _is_db_write(c)]
                if writes:
                    offenders.append(f"{path}:{log.lineno} ({fn.name}) after uncommitted writes at {writes}")
    assert offenders == []


async def test_log_leaves_callers_pending_work_to_the_caller(db_session, monkeypatch):
    from models.discussion import ActivityLog
    from tests.test_authz_boundaries import _make_engagement
    from utils.collaboration import create_activity_log
    eng = await _make_engagement(db_session)
    await db_session.commit()

    # Tests run automations inline on this session (conftest); in production
    # they run in the background on their own. Keep them out of the count.
    import utils.collaboration as collab

    async def _no_rules(*a, **k):
        return None
    monkeypatch.setattr(collab, "_evaluate_automations", _no_rules)

    commits = []
    real_commit = db_session.commit

    async def counting_commit():
        commits.append(1)
        return await real_commit()

    monkeypatch.setattr(db_session, "commit", counting_commit)
    eng.name = "renamed, not yet committed"
    await create_activity_log(db_session, engagement_id=eng.id, user_id=None, action="updated_engagement",
                              resource_type="engagement", resource_id=eng.id, resource_name="x")
    assert commits == []  # used to commit the rename along with the entry

    # With nothing pending it commits just its entry.
    await db_session.commit()
    commits.clear()
    await create_activity_log(db_session, engagement_id=eng.id, user_id=None, action="viewed",
                              resource_type="engagement", resource_id=eng.id, resource_name="x")
    assert commits == [1]
    logged = (await db_session.execute(select(ActivityLog.action).where(ActivityLog.resource_id == eng.id))).scalars().all()
    assert sorted(logged) == ["updated_engagement", "viewed"]


async def test_failed_log_keeps_callers_pending_work(db_session):
    from models.engagement import Engagement
    from tests.test_authz_boundaries import _make_engagement
    from utils.collaboration import create_activity_log
    eng = await _make_engagement(db_session)
    await db_session.commit()

    eng.description = "pending edit"
    # resource_id is NOT NULL: the insert fails inside its savepoint.
    await create_activity_log(db_session, engagement_id=eng.id, user_id=None, action="x",
                              resource_type="engagement", resource_id=None)
    await db_session.commit()  # the caller's work still commits
    got = (await db_session.execute(select(Engagement.description).where(Engagement.id == eng.id))).scalar_one()
    assert got == "pending edit"


async def test_deleted_engagement_log_keeps_its_origin(client, db_session, make_user, authenticate_as):
    from models.discussion import ActivityLog
    from tests.test_authz_boundaries import _make_engagement
    eng = await _make_engagement(db_session)
    eng_id = eng.id
    db_session.expunge_all()
    authenticate_as(await make_user(role="admin"))
    assert (await client.delete(f"/engagements/{eng_id}")).status_code == 204
    [row] = (await db_session.execute(select(ActivityLog).where(
        ActivityLog.action == "deleted_engagement", ActivityLog.resource_id == eng_id))).scalars().all()
    assert row.engagement_id is None and row.origin_engagement_id == eng_id


async def test_failed_delete_is_not_logged(client, db_session, make_user, authenticate_as, monkeypatch):
    """A delete that fails at commit leaves no 'deleted' audit entry."""
    from models.discussion import ActivityLog
    from tests.test_authz_boundaries import _make_engagement
    from models.spray import SprayCampaign
    eng = await _make_engagement(db_session)
    camp = SprayCampaign(id=str(uuid.uuid4()), engagement_id=eng.id, name="c")
    db_session.add(camp)
    await db_session.flush()
    camp_id = camp.id
    db_session.expunge_all()
    authenticate_as(await make_user(role="admin"))

    real_commit = db_session.commit
    state = {"n": 0}

    async def failing_commit():
        state["n"] += 1
        if state["n"] == 1:
            raise RuntimeError("commit failed")
        return await real_commit()

    monkeypatch.setattr(db_session, "commit", failing_commit)
    try:
        await client.delete(f"/spray/campaigns/{camp_id}")
    except RuntimeError:
        pass
    monkeypatch.setattr(db_session, "commit", real_commit)
    await db_session.rollback()
    logged = (await db_session.execute(select(ActivityLog).where(
        ActivityLog.action == "deleted_spray", ActivityLog.resource_id == camp_id))).scalars().all()
    assert logged == []
