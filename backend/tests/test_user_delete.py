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


async def test_delete_user_keeps_org_rules_and_reviews(client, db_session, make_user, authenticate_as):
    """Org automation rules and finding reviews used to be deleted with
    their author; they stay with the reference cleared. Personal rules
    still go with their owner."""
    from models.automation import AutomationRule
    from models.finding_review import FindingReview
    from tests.test_authz_boundaries import _make_finding
    eng = await _make_engagement(db_session)
    finding = await _make_finding(db_session, eng)
    gone = await make_user()
    org = AutomationRule(id=str(uuid.uuid4()), name="org", trigger_type="created_finding", created_by=gone.id,
                         conditions=[], actions=[])
    mine = AutomationRule(id=str(uuid.uuid4()), name="mine", trigger_type="created_finding", created_by=gone.id,
                          owner_user_id=gone.id, conditions=[], actions=[])
    review = FindingReview(id=str(uuid.uuid4()), finding_id=finding.id, reviewer_id=gone.id, status="APPROVED")
    db_session.add_all([org, mine, review])
    await db_session.flush()
    org_id, mine_id, review_id, finding_id = org.id, mine.id, review.id, finding.id

    authenticate_as(await make_user(role="admin"))
    assert (await client.delete(f"/admin/users/{gone.id}")).status_code == 204
    fresh = {"populate_existing": True}
    rules = {r.id: r for r in (await db_session.execute(select(AutomationRule).execution_options(**fresh))).scalars()}
    assert org_id in rules and rules[org_id].created_by is None and mine_id not in rules
    kept = (await db_session.execute(select(FindingReview).where(FindingReview.id == review_id).execution_options(**fresh))).scalar_one()
    assert kept.reviewer_id is None
    r = await client.get(f"/findings/{finding_id}/reviews")
    assert r.status_code == 200, r.text


async def test_delete_user_leaves_children_to_the_database(client, db_session, make_user, authenticate_as):
    """passive_deletes: deleting a user doesn't load their findings,
    engagements, events, assignments... — the FKs' ON DELETE does the work."""
    from sqlalchemy import event
    from models.finding import Finding
    from tests.test_authz_boundaries import _make_finding
    eng = await _make_engagement(db_session)
    gone = await make_user()
    ids = []
    for _ in range(3):
        f = await _make_finding(db_session, eng)
        f.created_by = gone.id
        ids.append(f.id)
    await db_session.flush()
    gone_id = gone.id
    authenticate_as(await make_user(role="admin"))

    seen = []
    engine = db_session.bind.sync_engine if hasattr(db_session.bind, "sync_engine") else db_session.bind

    def spy(conn, cursor, statement, params, context, executemany):
        seen.append(statement)
    event.listen(engine, "before_cursor_execute", spy)
    try:
        assert (await client.delete(f"/admin/users/{gone_id}")).status_code == 204
    finally:
        event.remove(engine, "before_cursor_execute", spy)
    child_selects = [s for s in seen if s.lstrip().upper().startswith("SELECT") and
                     any(f"FROM {t}" in s for t in ("findings", "engagements", "calendar_events", "user_skills"))]
    assert not child_selects, child_selects
    rows = (await db_session.execute(select(Finding.created_by).where(Finding.id.in_(ids))
                                     .execution_options(populate_existing=True))).scalars().all()
    assert rows == [None, None, None]
