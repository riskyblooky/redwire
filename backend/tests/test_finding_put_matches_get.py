"""PUT /findings/{id} returns the same body as a GET afterwards: it used to
return the bare ORM object, without creator fields, technique ids, the
unresolved-thread count or the per-asset port/remediation data."""

from __future__ import annotations


async def test_put_response_matches_get(client, db_session, make_user, authenticate_as):
    from tests.test_authz_boundaries import _make_engagement
    admin = await make_user(role="admin")
    eng = await _make_engagement(db_session, created_by=admin.id)
    authenticate_as(admin)
    asset = (await client.post("/assets", json={"engagement_id": eng.id, "name": "web01", "identifier": "10.0.0.5",
                                                "asset_type": "SERVER"})).json()
    fid = (await client.post("/findings", json={"engagement_id": eng.id, "title": "t", "severity": "LOW",
                                                "description": "d", "asset_ids": [asset["id"]]})).json()["id"]
    put = await client.put(f"/findings/{fid}", json={"title": "renamed", "attack_technique_ids": ["T1003"],
                                                     "status": "IN_REVIEW"})
    assert put.status_code == 200, put.text
    got = (await client.get(f"/findings/{fid}")).json()
    p = put.json()
    for k in ("updated_at",):
        p.pop(k, None); got.pop(k, None)
    assert p == got
    assert p["title"] == "renamed" and p["attack_technique_ids"] == ["T1003"]
    assert p["created_by_username"] == admin.username and p["assets"][0]["remediated"] is False
