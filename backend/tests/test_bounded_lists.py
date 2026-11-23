"""Thread, note and calendar lists take limit/offset (default and cap
MAX_LIST_LIMIT) instead of returning every row."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta


async def test_lists_page(client, db_session, make_user, authenticate_as):
    from models.calendar import CalendarEvent
    from models.discussion import Thread
    from models.note import Note
    from tests.test_authz_boundaries import _make_engagement
    admin = await make_user(role="admin")
    eng = await _make_engagement(db_session, created_by=admin.id)
    t0 = datetime(2030, 1, 1)
    for i in range(3):
        db_session.add(Note(id=str(uuid.uuid4()), engagement_id=eng.id, title=f"n{i}", content="c", created_by=admin.id))
        db_session.add(Thread(id=str(uuid.uuid4()), engagement_id=eng.id, resource_type="engagement",
                              resource_id=eng.id, title=f"t{i}", created_by=admin.id))
        db_session.add(CalendarEvent(id=str(uuid.uuid4()), title=f"e{i}", start_time=t0 + timedelta(days=i),
                                     end_time=t0 + timedelta(days=i, hours=1), created_by=admin.id))
    await db_session.flush()
    authenticate_as(admin)
    notes = (await client.get(f"/engagements/{eng.id}/notes", params={"limit": 2})).json()
    assert len(notes) == 2
    assert len((await client.get(f"/engagements/{eng.id}/notes", params={"limit": 2, "offset": 2})).json()) == 1
    assert len((await client.get("/discussions/threads", params={"engagement_id": eng.id, "limit": 2})).json()) == 2
    rng = {"start": "2030-01-01T00:00:00", "end": "2030-01-10T00:00:00"}
    ev = (await client.get("/calendar/events", params={**rng, "limit": 2, "offset": 1})).json()
    assert [e["title"] for e in ev] == ["e1", "e2"]
    assert (await client.get("/calendar/events", params={"limit": 100000})).status_code == 422
