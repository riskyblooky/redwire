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


async def test_compare_counts_findings_of_engagements_without_a_client(client, db_session, make_user,
                                                                        authenticate_as):
    from tests.test_authz_boundaries import _make_finding
    admin = await make_user(role="admin")
    a = await _make_engagement(db_session, client_id=None)
    b = await _make_engagement(db_session, client_id=None)
    await _make_finding(db_session, b)
    await _make_finding(db_session, b)
    authenticate_as(admin)

    r = await client.get("/engagements/compare/summary", params={"a": a.id, "b": b.id})

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["b"]["finding_count"] == 2 and body["a"]["finding_count"] == 0


async def test_compare_hides_engagements_the_caller_cannot_view(client, db_session, make_user, authenticate_as):
    outsider = await make_user()
    a, b = await _make_engagement(db_session), await _make_engagement(db_session)
    authenticate_as(outsider)
    r = await client.get("/engagements/compare/summary", params={"a": a.id, "b": b.id})
    assert r.status_code == 404
