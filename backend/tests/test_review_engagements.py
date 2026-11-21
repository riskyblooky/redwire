"""Review sweep: clients, engagements, findings."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from tests.test_authz_boundaries import _make_engagement


async def test_client_rename_reaches_its_engagements(client, db_session, make_user, authenticate_as):
    from models.client import Client
    from models.engagement import Engagement
    admin = await make_user(role="admin")
    c = Client(id=str(uuid.uuid4()), name=f"Old {uuid.uuid4().hex[:6]}")
    db_session.add(c)
    await db_session.flush()
    eng = await _make_engagement(db_session, client_id=c.id, client_name=c.name)
    authenticate_as(admin)
    new = f"New {uuid.uuid4().hex[:6]}"

    r = await client.put(f"/clients/{c.id}", json={"name": new})

    assert r.status_code == 200, r.text
    name = (await db_session.execute(select(Engagement.client_name).where(Engagement.id == eng.id)
                                     .execution_options(populate_existing=True))).scalar_one()
    assert name == new
