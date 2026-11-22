"""ThreadUpdate: an explicit null title / is_resolved is a 422, not a 500."""

from __future__ import annotations

import uuid

from models.discussion import Thread
from tests.test_authz_boundaries import _make_engagement


async def test_thread_update_nulls_rejected(client, db_session, make_user, authenticate_as):
    admin = await make_user(role="admin")
    authenticate_as(admin)
    eng = await _make_engagement(db_session)
    t = Thread(id=str(uuid.uuid4()), engagement_id=eng.id, resource_type="engagement", title="t", created_by=admin.id)
    db_session.add(t)
    await db_session.flush()
    for body in ({"title": None}, {"is_resolved": None}):
        r = await client.put(f"/discussions/threads/{t.id}", json=body)
        assert r.status_code == 422, (body, r.status_code, r.text)
    assert (await client.put(f"/discussions/threads/{t.id}", json={"title": "ok"})).status_code == 200
