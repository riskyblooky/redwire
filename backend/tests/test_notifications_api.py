"""Notifications are per user: listing, browsing, counting, marking,
deleting, clearing and preferences only ever see or touch the caller's own
rows; another user's notification id is a 404 and stays as it was."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select


async def _notify(db, user, title, read=False):
    from models.notification import Notification
    n = Notification(id=str(uuid.uuid4()), user_id=user.id, event_type="finding_created", title=title, is_read=read)
    db.add(n)
    await db.flush()
    return n


@pytest.fixture
async def pair(db_session, make_user):
    alice, bob = await make_user(), await make_user()
    a1 = await _notify(db_session, alice, "alice one")
    a2 = await _notify(db_session, alice, "alice two", read=True)
    b1 = await _notify(db_session, bob, "bob one")
    await db_session.commit()
    return alice, bob, a1, a2, b1


async def _state(db, n):
    from models.notification import Notification
    db.expunge_all()
    row = (await db.execute(select(Notification).where(Notification.id == n.id))).scalar_one_or_none()
    return None if row is None else row.is_read


async def test_reads_are_own_only(client, authenticate_as, pair):
    alice, bob, a1, a2, b1 = pair
    authenticate_as(alice)
    assert {n["title"] for n in (await client.get("/notifications")).json()} == {"alice one", "alice two"}
    assert [n["title"] for n in (await client.get("/notifications", params={"unread_only": True})).json()] == ["alice one"]
    assert (await client.get("/notifications/unread-count")).json() == {"count": 1}
    browse = (await client.get("/notifications/browse", params={"search": "one"})).json()
    assert browse["total"] == 1 and [i["title"] for i in browse["items"]] == ["alice one"]


async def test_another_users_notification_is_404_and_unchanged(client, db_session, authenticate_as, pair):
    alice, bob, a1, a2, b1 = pair
    authenticate_as(alice)
    for method, url in (("patch", f"/notifications/{b1.id}/read"), ("patch", f"/notifications/{b1.id}/unread"),
                        ("delete", f"/notifications/{b1.id}")):
        r = await getattr(client, method)(url)
        assert r.status_code == 404, (url, r.status_code)
    assert await _state(db_session, b1) is False, "bob's notification was touched"

    assert (await client.patch(f"/notifications/{a1.id}/read")).status_code == 200
    assert await _state(db_session, a1) is True
    assert (await client.patch(f"/notifications/{a1.id}/unread")).status_code == 200
    assert await _state(db_session, a1) is False
    assert (await client.delete(f"/notifications/{a2.id}")).status_code == 200
    assert await _state(db_session, a2) is None


async def test_bulk_actions_are_own_only(client, db_session, authenticate_as, pair):
    alice, bob, a1, a2, b1 = pair
    authenticate_as(alice)
    assert (await client.post("/notifications/mark-all-read")).status_code == 200
    assert await _state(db_session, a1) is True and await _state(db_session, b1) is False
    assert (await client.post("/notifications/clear-all")).status_code == 200
    assert await _state(db_session, a1) is None and await _state(db_session, a2) is None
    assert await _state(db_session, b1) is False, "clear-all removed another user's notification"


async def test_preferences_are_per_user_and_ignore_unknown_events(client, authenticate_as, pair):
    alice, bob, *_ = pair
    authenticate_as(alice)
    r = await client.put("/notifications/preferences", json=[
        {"event_type": "finding_created", "site_muted": True, "email_muted": True},
        {"event_type": "no_such_event", "site_muted": True, "email_muted": True},
    ])
    assert r.status_code == 200, r.text
    prefs = {p["event_type"]: p for p in (await client.get("/notifications/preferences")).json()}
    assert prefs["finding_created"]["site_muted"] is True and "no_such_event" not in prefs

    authenticate_as(bob)
    prefs = {p["event_type"]: p for p in (await client.get("/notifications/preferences")).json()}
    assert prefs["finding_created"]["site_muted"] is False, "alice's preference leaked to bob"
