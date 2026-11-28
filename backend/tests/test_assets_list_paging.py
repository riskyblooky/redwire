"""GET /assets as a server-paged list: the filters the assets tab used to
apply to one page in the browser now apply on the server, the total is in
both the body and X-Total-Count, search ranks whole matches first and
escapes LIKE wildcards, and /assets/facets lists the creators."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from models.asset import Asset
from models.asset_port import AssetPort, PortProtocol, PortState
from tests.test_authz_boundaries import _make_engagement


@pytest.fixture
async def eng(db_session, make_user):
    e = await _make_engagement(db_session)
    alice = await make_user(username=f"alice-{uuid.uuid4().hex[:6]}")
    now = datetime.utcnow()
    specs = [
        ("dc", "IP Address", True, False, False, alice.id, 0),
        ("dc01", "IP Address", True, True, True, None, 1),
        ("web-dc-proxy", "Domain", False, False, False, alice.id, 2),
        ("100%_host", "Server", True, False, False, None, 3),
    ]
    rows = {}
    for name, typ, scope, scanned, pwned, creator, age in specs:
        a = Asset(id=str(uuid.uuid4()), engagement_id=e.id, name=name, asset_type=typ, identifier=f"{name}.corp",
                  in_scope=scope, is_scanned=scanned, is_pwned=pwned, created_by=creator,
                  created_at=now - timedelta(days=age))
        db_session.add(a)
        rows[name] = a
    await db_session.flush()
    db_session.add(AssetPort(id=str(uuid.uuid4()), asset_id=rows["dc01"].id, port_number=445,
                             protocol=PortProtocol.TCP, state=PortState.OPEN, service_name="microsoft-ds"))
    await db_session.commit()
    return e, alice


def _names(r):
    assert r.status_code == 200, r.text
    body = r.json()
    assert r.headers["X-Total-Count"] == str(body["total"])
    return [a["name"] for a in body["items"]]


async def test_server_side_filters(client, make_user, authenticate_as, eng):
    e, alice = eng
    authenticate_as(await make_user(role="admin"))
    base = {"engagement_id": e.id, "sort_by": "name"}
    assert _names(await client.get("/assets", params={**base, "in_scope": "false"})) == ["web-dc-proxy"]
    assert _names(await client.get("/assets", params={**base, "is_pwned": "true"})) == ["dc01"]
    assert _names(await client.get("/assets", params={**base, "is_scanned": "false", "limit": 1})) == ["100%_host"]
    r = await client.get("/assets", params={**base, "is_scanned": "false", "limit": 1})
    assert r.json()["total"] == 3, "the total counts every match, not the page"
    assert _names(await client.get("/assets", params={**base, "asset_type": ["Domain", "Server"]})) == \
        ["100%_host", "web-dc-proxy"]
    assert _names(await client.get("/assets", params={**base, "created_by": alice.username})) == ["dc", "web-dc-proxy"]
    assert _names(await client.get("/assets", params={**base, "port": 445})) == ["dc01"]
    assert _names(await client.get("/assets", params={**base, "q": "microsoft"})) == ["dc01"], "port service text"


async def test_ranked_and_escaped_search(client, make_user, authenticate_as, eng):
    e, _ = eng
    authenticate_as(await make_user(role="admin"))
    # "search" is the old name of q.
    assert _names(await client.get("/assets", params={"engagement_id": e.id, "search": "dc"})) == \
        ["dc", "web-dc-proxy", "dc01"]
    assert _names(await client.get("/assets", params={"engagement_id": e.id, "q": "100%"})) == ["100%_host"]
    assert _names(await client.get("/assets", params={"engagement_id": e.id, "q": "%"})) == ["100%_host"]


async def test_facets(client, make_user, authenticate_as, eng):
    e, alice = eng
    authenticate_as(await make_user(role="admin"))
    facets = (await client.get("/assets/facets", params={"engagement_id": e.id})).json()
    assert facets["total"] == 4
    assert [c["username"] for c in facets["creators"]] == [alice.username]
