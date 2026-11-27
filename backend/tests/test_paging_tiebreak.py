"""Paged lists stay stable when rows share a sort key, and the test case
list reports its total."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from tests.test_authz_boundaries import _make_engagement


async def test_notification_pages_with_equal_timestamps(client, db_session, make_user, authenticate_as):
    from models.notification import Notification
    me = await make_user(role="operator")
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc).replace(tzinfo=None)
    ids = set()
    for i in range(9):
        n = Notification(id=str(uuid.uuid4()), user_id=me.id, event_type="probe", title=f"n{i}", created_at=ts)
        db_session.add(n)
        ids.add(n.id)
    await db_session.flush()
    authenticate_as(me)
    seen = []
    for skip in range(0, 9, 2):
        r = await client.get("/notifications", params={"skip": skip, "limit": 2})
        assert r.status_code == 200, r.text
        seen += [x["id"] for x in r.json()]
    assert len(seen) == 9 and set(seen) == ids


async def test_testcase_list_total_header(client, db_session, make_user, authenticate_as):
    from models.testcase import TestCase
    eng = await _make_engagement(db_session)
    admin = await make_user(role="admin")
    for i in range(5):
        db_session.add(TestCase(id=str(uuid.uuid4()), engagement_id=eng.id, title=f"tc{i}",
                                category="Recon", description="d", created_by=admin.id))
    await db_session.flush()
    authenticate_as(admin)
    r = await client.get("/testcases", params={"engagement_id": eng.id, "limit": 2})
    assert r.status_code == 200, r.text
    assert len(r.json()) == 2 and r.headers["X-Total-Count"] == "5"
