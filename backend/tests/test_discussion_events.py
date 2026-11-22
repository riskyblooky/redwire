"""Discussion events: a reopen broadcasts "reopened_thread", a comment edit
broadcasts, and an enum resource type is logged as its value."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from models.discussion import ActivityLog, Comment, Thread
from routers import discussions
from tests.test_authz_boundaries import _make_engagement


async def test_reopen_and_edit_broadcast(client, db_session, make_user, authenticate_as, monkeypatch):
    admin = await make_user(role="admin")
    authenticate_as(admin)
    eng = await _make_engagement(db_session)
    t = Thread(id=str(uuid.uuid4()), engagement_id=eng.id, resource_type="engagement", title="t",
               created_by=admin.id, is_resolved=True)
    c = Comment(id=str(uuid.uuid4()), thread_id=t.id, content="hi", created_by=admin.id)
    db_session.add(t)
    await db_session.flush()
    db_session.add(c)
    await db_session.flush()
    sent = []

    async def fake(eid, tid, action):
        sent.append(action)
    monkeypatch.setattr(discussions, "_broadcast_discussion_update", fake)

    assert (await client.put(f"/discussions/threads/{t.id}/resolve")).status_code == 200   # toggles: reopen
    assert (await client.put(f"/discussions/comments/{c.id}", json={"content": "edited"})).status_code == 200
    assert sent == ["reopened_thread", "updated_comment"]

    rt = (await db_session.execute(select(ActivityLog.resource_type).where(ActivityLog.resource_id == t.id))).scalars().all()
    assert rt and all(r == "thread" for r in rt), rt


async def test_enum_resource_type_plugin_event_name(db_session, make_user, monkeypatch):
    from models.discussion import ResourceType
    from utils import collaboration
    from utils.event_bus import event_bus
    names = []

    async def emit(name, payload):
        names.append(name)
    monkeypatch.setattr(event_bus, "emit", emit)
    user = await make_user(role="admin")
    await collaboration.create_activity_log(
        db_session, engagement_id=None, user_id=user.id, action="created_thread",
        resource_type=ResourceType.THREAD, resource_id=str(uuid.uuid4()))
    assert names == ["thread.created"]
