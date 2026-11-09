"""Live field auto-save (utils/collab_fields.save_collab_field) and asset
version history: one version + one activity entry per live-editing session,
restores refused while someone else edits live."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select

import database
from models.asset import Asset
from models.discussion import ActivityLog
from models.engagement import Engagement
from models.finding import Finding
from models.report_layout import ReportLayout, ReportSection, SectionType
from models.version_history import VersionHistory
from utils.collab_fields import save_collab_field


@pytest.fixture
def shared_session(db_session, monkeypatch):
    """save_collab_field opens its own session — hand it the test one."""
    class _Ctx:
        async def __aenter__(self):
            return db_session

        async def __aexit__(self, *exc):
            return False
    monkeypatch.setattr(database, "AsyncSessionLocal", lambda: _Ctx())
    return db_session


async def _engagement(db, make_user):
    user = await make_user(role="admin", username=f"la_{uuid.uuid4().hex[:6]}")
    eng = Engagement(id=str(uuid.uuid4()), name="Live", client_name="ACME",
                     engagement_type="external_pentest", created_by=user.id)
    db.add(eng)
    await db.flush()
    return user, eng


async def _counts(db, entity_type, entity_id):
    versions = (await db.execute(select(func.count()).select_from(VersionHistory).where(
        VersionHistory.entity_type == entity_type, VersionHistory.entity_id == entity_id))).scalar()
    logs = (await db.execute(select(func.count()).select_from(ActivityLog).where(
        ActivityLog.resource_type == entity_type, ActivityLog.resource_id == entity_id))).scalar()
    return versions, logs


async def test_session_coalescing(shared_session, make_user):
    db = shared_session
    user, eng = await _engagement(db, make_user)
    f = Finding(id=str(uuid.uuid4()), engagement_id=eng.id, title="F", description="old",
                severity="LOW", created_by=user.id)
    db.add(f)
    await db.flush()

    assert await save_collab_field("finding", f.id, "description", "old plus", user.id)
    assert await save_collab_field("finding", f.id, "description", "old plus more", user.id)
    assert await save_collab_field("finding", f.id, "description", "old plus more", user.id)  # no-op
    await db.refresh(f)
    assert f.description == "old plus more"
    assert await _counts(db, "finding", f.id) == (1, 1)
    v = (await db.execute(select(VersionHistory).where(VersionHistory.entity_id == f.id))).scalar_one()
    assert v.snapshot["description"] == "old" and v.changed_fields == ["description"]

    # Another field is its own session.
    assert await save_collab_field("finding", f.id, "impact", "bad", user.id)
    assert await _counts(db, "finding", f.id) == (2, 2)


async def test_other_targets(shared_session, make_user):
    db = shared_session
    user, eng = await _engagement(db, make_user)
    layout = ReportLayout(id=str(uuid.uuid4()), engagement_id=eng.id, name="L")
    db.add(layout)
    await db.flush()
    sec = ReportSection(id=str(uuid.uuid4()), report_layout_id=layout.id, title="Exec",
                        section_type=SectionType.TEXT, content="a")
    db.add(sec)
    await db.flush()
    assert await save_collab_field("report_section", sec.id, "content", "a b", user.id)
    await db.refresh(sec)
    assert sec.content == "a b"

    assert not await save_collab_field("finding", str(uuid.uuid4()), "description", "x", user.id)
    assert not await save_collab_field("finding", str(uuid.uuid4()), "title", "x", user.id)  # not live


async def test_asset_versions_and_restore(client, db_session, make_user, authenticate_as, monkeypatch):
    user, eng = await _engagement(db_session, make_user)
    authenticate_as(user)
    a = Asset(id=str(uuid.uuid4()), engagement_id=eng.id, name="web01", asset_type="Server",
              identifier="10.0.0.1", created_by=user.id)
    db_session.add(a)
    await db_session.flush()

    r = await client.put(f"/assets/{a.id}", json={"name": "web01-prod"})
    assert r.status_code == 200, r.text
    versions = (await client.get(f"/assets/{a.id}/versions")).json()
    assert len(versions) == 1 and versions[0]["changed_fields"] == ["name"]
    snap = (await client.get(f"/assets/{a.id}/versions/{versions[0]['id']}")).json()
    assert snap["snapshot"]["name"] == "web01"

    # Someone else has a field open live → restore refused.
    from utils.ws_bus import bus

    async def _others(kind, key):
        return [{"id": "someone-else"}] if key.endswith(":notes") else []
    monkeypatch.setattr(bus, "presence_list", _others)
    r = await client.post(f"/assets/{a.id}/versions/{versions[0]['id']}/restore")
    assert r.status_code == 409

    async def _self_only(kind, key):
        return [{"id": user.id}]
    monkeypatch.setattr(bus, "presence_list", _self_only)
    r = await client.post(f"/assets/{a.id}/versions/{versions[0]['id']}/restore")
    assert r.status_code == 200, r.text
    assert (await client.get(f"/assets/{a.id}")).json()["name"] == "web01"
    assert len((await client.get(f"/assets/{a.id}/versions")).json()) == 2


async def test_every_live_save_announces_record_updated(shared_session, make_user, monkeypatch):
    """Each save (not just a session's first, which also logs activity) tells
    the record's presence channel, so view pages refetch the field."""
    from utils.collaboration import manager
    sent = []

    async def capture(rtype, rid, message, db=None):
        sent.append((rtype, rid, message))
    monkeypatch.setattr(manager, "broadcast_to_resource", capture)
    db = shared_session
    user, eng = await _engagement(db, make_user)
    f = Finding(id=str(uuid.uuid4()), engagement_id=eng.id, title="F", description="a",
                severity="LOW", created_by=user.id)
    db.add(f)
    await db.flush()
    for text in ("ab", "abc", "abc"):  # last one is a no-op and announces nothing
        await save_collab_field("finding", f.id, "description", text, user.id)
    updates = [m for rt, rid, m in sent if (rt, rid) == ("finding", f.id) and m["type"] == "record_updated"]
    assert [u["field"] for u in updates] == ["description", "description"]
    activity = [m for _rt, _rid, m in sent if m["type"] == "activity_log"]
    assert activity and activity[0]["resource_id"] == f.id
