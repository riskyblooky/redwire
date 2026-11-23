"""attack_graph.py gates through require_engagement_perm (it hand-rolled
the same checks thirteen times): view lets the read-bypass roles in,
edits need the write-bypass roles or the engagement permission."""

from __future__ import annotations

import uuid


async def _engagement(db, owner):
    from models.engagement import Engagement
    eng = Engagement(id=str(uuid.uuid4()), name=f"G-{uuid.uuid4().hex[:6]}", client_name="ACME",
                     engagement_type="external_pentest", created_by=owner.id)
    db.add(eng)
    await db.flush()
    return eng.id


async def test_attack_graph_gates(client, db_session, make_user, authenticate_as):
    admin = await make_user(role="admin")
    eid = await _engagement(db_session, admin)
    layout = {"name": "L", "positions": {"n1": {"x": 1, "y": 2}}}

    authenticate_as(await make_user(role="read_only_admin"))
    assert (await client.get(f"/engagements/{eid}/attack-graph")).status_code == 200
    denied = await client.post(f"/engagements/{eid}/attack-graph/layouts", json=layout)
    assert denied.status_code == 403 and "engagement_edit" in denied.json()["detail"]

    authenticate_as(await make_user(role="operator"))  # not a member
    assert (await client.get(f"/engagements/{eid}/attack-graph")).status_code == 403

    authenticate_as(await make_user(role="team_lead"))
    assert (await client.post(f"/engagements/{eid}/attack-graph/layouts", json=layout)).status_code in (200, 201)
