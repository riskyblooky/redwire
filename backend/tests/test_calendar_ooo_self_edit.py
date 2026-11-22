"""An OOO block is self-service: its creator can edit it without the
calendar_edit permission (create and delete already allowed that), and
still can't edit someone else's."""

from __future__ import annotations


async def test_creator_edits_own_ooo_without_calendar_edit(client, make_user, authenticate_as):
    me = await make_user(role="operator")
    other = await make_user(role="operator")
    ooo = {"title": "Leave", "event_type": "OOO", "start_time": "2026-12-01T00:00:00", "end_time": "2026-12-02T00:00:00"}
    authenticate_as(me)
    r = await client.post("/calendar/events", json=ooo)
    assert r.status_code == 201, r.text
    eid = r.json()["id"]
    r = await client.put(f"/calendar/events/{eid}", json={"end_time": "2026-12-03T00:00:00"})
    assert r.status_code == 200, r.text

    authenticate_as(other)
    assert (await client.put(f"/calendar/events/{eid}", json={"title": "x"})).status_code == 403
