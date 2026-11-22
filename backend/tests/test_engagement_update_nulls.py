"""Engagement update: an explicit null / blank for a required column is a
422 and changes nothing (a null name used to be saved as "" and then 500),
and client_id "" unlinks the client instead of failing the foreign key."""

from __future__ import annotations

from sqlalchemy import select

from models.engagement import Engagement
from tests.test_authz_boundaries import _make_engagement


async def test_required_nulls_rejected_and_blank_client_unlinks(client, db_session, make_user, authenticate_as):
    authenticate_as(await make_user(role="admin"))
    eng = await _make_engagement(db_session)
    name = eng.name
    for body in ({"name": None}, {"name": "  "}, {"client_name": None}):
        r = await client.put(f"/engagements/{eng.id}", json=body)
        assert r.status_code == 422, (body, r.status_code, r.text)
    row = (await db_session.execute(select(Engagement).where(Engagement.id == eng.id)
                                    .execution_options(populate_existing=True))).scalar_one()
    assert row.name == name

    r = await client.put(f"/engagements/{eng.id}", json={"client_id": ""})
    assert r.status_code == 200, r.text
    assert r.json()["client_id"] is None
