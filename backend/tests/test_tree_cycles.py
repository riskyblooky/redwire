"""Test-case and note re-parenting rejects cycles; cascade delete survives
one already in the data."""

from __future__ import annotations

import uuid

from tests.test_authz_boundaries import _make_engagement


async def _tc(db, eng, parent=None):
    from models.testcase import TestCase
    tc = TestCase(id=str(uuid.uuid4()), engagement_id=eng.id, title="t", category="c", description="d",
                  parent_id=parent.id if parent else None)
    db.add(tc)
    await db.flush()
    return tc


async def test_testcase_cannot_move_under_descendant(client, db_session, make_user, authenticate_as):
    eng = await _make_engagement(db_session)
    a = await _tc(db_session, eng)
    b = await _tc(db_session, eng, a)
    c = await _tc(db_session, eng, b)
    authenticate_as(await make_user(role="admin"))
    r = await client.put(f"/testcases/{a.id}", json={"parent_id": c.id})
    assert r.status_code == 400 and "sub-cases" in r.json()["detail"]


async def test_cascade_delete_terminates_on_existing_cycle(client, db_session, make_user, authenticate_as):
    eng = await _make_engagement(db_session)
    a = await _tc(db_session, eng)
    b = await _tc(db_session, eng, a)
    a.parent_id = b.id  # cycle that predates the check
    await db_session.flush()
    authenticate_as(await make_user(role="admin"))
    r = await client.delete(f"/testcases/{a.id}", params={"cascade": True}, timeout=10)
    assert r.status_code == 204


async def test_note_cannot_move_under_descendant(client, db_session, make_user, authenticate_as):
    from models.note import Note
    eng = await _make_engagement(db_session)
    a = Note(id=str(uuid.uuid4()), engagement_id=eng.id, title="a")
    db_session.add(a)
    await db_session.flush()
    b = Note(id=str(uuid.uuid4()), engagement_id=eng.id, title="b", parent_id=a.id)
    db_session.add(b)
    await db_session.flush()
    authenticate_as(await make_user(role="admin"))
    r = await client.patch(f"/notes/{a.id}", json={"parent_id": b.id})
    assert r.status_code == 400
