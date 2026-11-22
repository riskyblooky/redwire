"""Legacy layout PUT is size-capped like the named-layout routes, and the
layout list keeps layouts whose pinning user was deleted."""

from __future__ import annotations

import uuid

from models.attack_graph_layout import AttackGraphLayout
from schemas._field_limits import MAX_GRAPH_NODES
from tests.test_authz_boundaries import _make_engagement


async def test_legacy_put_capped_and_orphan_layout_listed(client, db_session, make_user, authenticate_as):
    authenticate_as(await make_user(role="admin"))
    eng = await _make_engagement(db_session)
    big = {f"n{i}": {"x": 0, "y": 0} for i in range(MAX_GRAPH_NODES + 1)}
    r = await client.put(f"/engagements/{eng.id}/attack-graph/layout", json={"positions": big})
    assert r.status_code == 400, r.status_code

    db_session.add(AttackGraphLayout(id=str(uuid.uuid4()), engagement_id=eng.id, name="Old",
                                     positions='{"a": {"x": 1, "y": 1}}', pinned_by=None))
    await db_session.flush()
    listed = (await client.get(f"/engagements/{eng.id}/attack-graph/layouts")).json()
    assert [(l["name"], l["pinned_by_username"]) for l in listed] == [("Old", None)]
