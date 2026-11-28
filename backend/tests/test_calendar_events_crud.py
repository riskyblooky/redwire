"""Shared (non-OOO) calendar events: each of view / create / edit / delete
needs its own global permission (an OOO block is self-service and covered in
test_calendar_ooo_self_edit). A refused write changes nothing; the range
query returns the events overlapping the window; event_type is frozen at
create time."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from tests.test_security_center import _grant

EVENT = {"title": "Kickoff", "start_time": "2026-12-01T09:00:00", "end_time": "2026-12-01T10:00:00",
         "event_type": "EVENT"}


async def _user(db, make_user, *perms):
    u = await make_user()
    if perms:
        await _grant(db, u, *perms)
    await db.commit()
    return u


async def _event(db, event_id):
    from models.calendar import CalendarEvent
    db.expunge_all()
    return (await db.execute(select(CalendarEvent).where(CalendarEvent.id == event_id))).scalar_one_or_none()


async def test_each_action_needs_its_own_permission(client, db_session, make_user, authenticate_as):
    nobody = await _user(db_session, make_user)
    viewer = await _user(db_session, make_user, "calendar_view")
    creator = await _user(db_session, make_user, "calendar_create")
    editor = await _user(db_session, make_user, "calendar_edit")
    deleter = await _user(db_session, make_user, "calendar_delete")

    authenticate_as(nobody)
    assert (await client.get("/calendar/events")).status_code == 403
    assert (await client.post("/calendar/events", json=EVENT)).status_code == 403

    authenticate_as(creator)
    r = await client.post("/calendar/events", json=EVENT)
    assert r.status_code == 201, r.text
    eid = r.json()["id"]
    assert (await client.get("/calendar/events")).status_code == 403, "create doesn't imply view"

    authenticate_as(viewer)
    assert eid in {e["id"] for e in (await client.get("/calendar/events")).json()}
    for who in (viewer, creator, deleter):
        authenticate_as(who)
        assert (await client.put(f"/calendar/events/{eid}", json={"title": "Moved"})).status_code == 403
    assert (await _event(db_session, eid)).title == "Kickoff"
    for who in (viewer, creator, editor):
        authenticate_as(who)
        assert (await client.delete(f"/calendar/events/{eid}")).status_code == 403
    assert await _event(db_session, eid) is not None

    authenticate_as(editor)
    r = await client.put(f"/calendar/events/{eid}", json={"title": "Moved", "event_type": "OOO"})
    assert r.status_code == 200 and r.json()["title"] == "Moved"
    assert (await _event(db_session, eid)).event_type == "EVENT", "event_type is frozen at create"

    authenticate_as(deleter)
    assert (await client.delete(f"/calendar/events/{eid}")).status_code == 204
    assert await _event(db_session, eid) is None
    assert (await client.delete(f"/calendar/events/{eid}")).status_code == 404


@pytest.mark.parametrize("window,hit", [
    (("2026-12-01T09:30:00", "2026-12-01T09:45:00"), True),   # inside
    (("2026-12-01T08:00:00", "2026-12-01T09:00:00"), True),   # touches the start
    (("2026-12-01T10:00:00", "2026-12-01T11:00:00"), True),   # touches the end
    (("2026-12-01T10:00:01", "2026-12-02T00:00:00"), False),  # after
    (("2026-11-30T00:00:00", "2026-12-01T08:59:59"), False),  # before
    (("2026-12-01T09:30:00+05:00", "2026-12-01T09:45:00+05:00"), True),  # zone dropped: wall clock
])
async def test_range_query_returns_overlapping_events(client, db_session, make_user, authenticate_as, window, hit):
    authenticate_as(await make_user(role="admin"))
    eid = (await client.post("/calendar/events", json=EVENT)).json()["id"]
    got = {e["id"] for e in (await client.get("/calendar/events",
                                              params={"start": window[0], "end": window[1]})).json()}
    assert (eid in got) is hit
