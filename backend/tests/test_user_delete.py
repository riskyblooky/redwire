"""A user with history can be deleted: their audit rows, notes, threads and
comments stay, with the author reference cleared."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from tests.test_authz_boundaries import _make_engagement


async def test_delete_user_with_history_keeps_records(client, db_session, make_user, authenticate_as):
    from models.discussion import ActivityLog, Comment, Thread
    from models.note import Note
    eng = await _make_engagement(db_session)
    gone = await make_user()
    note = Note(id=str(uuid.uuid4()), engagement_id=eng.id, title="recon", content="x", created_by=gone.id)
    thread = Thread(id=str(uuid.uuid4()), engagement_id=eng.id, resource_type="note", resource_id=note.id,
                    title="t", created_by=gone.id)
    db_session.add_all([note, thread])
    await db_session.flush()
    comment = Comment(id=str(uuid.uuid4()), thread_id=thread.id, content="hi", created_by=gone.id)
    log = ActivityLog(engagement_id=eng.id, user_id=gone.id, action="created_note", resource_type="note",
                      resource_id=note.id)
    db_session.add_all([comment, log])
    await db_session.flush()

    authenticate_as(await make_user(role="admin"))
    assert (await client.delete(f"/admin/users/{gone.id}")).status_code == 204

    for model, col in ((Note, Note.created_by), (Thread, Thread.created_by), (Comment, Comment.created_by),
                       (ActivityLog, ActivityLog.user_id)):
        rows = (await db_session.execute(select(model).where(model.id.in_([note.id, thread.id, comment.id, log.id]))
                                         .execution_options(populate_existing=True))).scalars().all()
        assert len(rows) == 1 and getattr(rows[0], col.key) is None, model.__name__

    feed = (await client.get("/discussions/activity/feed", params={"engagement_id": eng.id, "include_all": True})).json()
    assert feed["items"][0]["user_name"] == "Deleted user"
