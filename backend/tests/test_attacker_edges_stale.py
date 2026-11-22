"""An attacker edge whose target was deleted isn't emitted (the graph drew
it to a node that doesn't exist) and the stale row is removed."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from models.asset import Asset
from models.attacker_node import AttackerNode, AttackerNodeEdge
from tests.test_authz_boundaries import _make_engagement


async def test_stale_attacker_edge_dropped(client, db_session, make_user, authenticate_as):
    authenticate_as(await make_user(role="admin"))
    eng = await _make_engagement(db_session)
    asset = Asset(id=str(uuid.uuid4()), engagement_id=eng.id, name="web", asset_type="Server", identifier="10.0.0.5")
    an = AttackerNode(id=str(uuid.uuid4()), engagement_id=eng.id)
    db_session.add_all([asset, an])
    await db_session.flush()
    live = AttackerNodeEdge(attacker_node_id=an.id, target_node_id=f"asset-{asset.id}", target_node_type="asset")
    gone = AttackerNodeEdge(attacker_node_id=an.id, target_node_id=f"asset-{uuid.uuid4()}", target_node_type="asset")
    db_session.add_all([live, gone])
    await db_session.flush()

    r = await client.get(f"/engagements/{eng.id}/attack-graph")
    assert r.status_code == 200, r.text
    attack = [e for e in r.json()["edges"] if e.get("label") == "attacks"]
    assert [e["target"] for e in attack] == [f"asset-{asset.id}"]
    left = (await db_session.execute(select(AttackerNodeEdge.id).where(AttackerNodeEdge.attacker_node_id == an.id))).scalars().all()
    assert left == [live.id]
