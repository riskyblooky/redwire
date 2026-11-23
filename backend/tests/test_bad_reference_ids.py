"""Ids in a request that name nothing are the client's mistake: 422, not 500.
Duplicate ATT&CK technique ids collapse instead of breaking the insert."""

from __future__ import annotations

import uuid


async def test_unknown_client_type_is_422(client, db_session, make_user, authenticate_as):
    authenticate_as(await make_user(role="admin"))
    r = await client.post("/clients", json={"name": f"c-{uuid.uuid4().hex[:6]}", "client_type_id": str(uuid.uuid4())})
    assert r.status_code == 422 and "client_type_id" in r.json()["detail"], r.text


async def test_unknown_marking_profile_is_422(client, db_session, make_user, authenticate_as):
    from tests.test_authz_boundaries import _make_engagement
    admin = await make_user(role="admin")
    eng = await _make_engagement(db_session, created_by=admin.id)
    authenticate_as(admin)
    r = await client.put(f"/engagements/{eng.id}", json={"marking_profile_id": str(uuid.uuid4())})
    assert r.status_code == 422 and "marking_profile_id" in r.json()["detail"], r.text


async def test_duplicate_technique_ids_collapse(client, db_session, make_user, authenticate_as):
    from tests.test_authz_boundaries import _make_engagement
    admin = await make_user(role="admin")
    eng = await _make_engagement(db_session, created_by=admin.id)
    authenticate_as(admin)
    r = await client.post("/findings", json={"engagement_id": eng.id, "title": "t", "severity": "LOW",
                                             "description": "d", "attack_technique_ids": ["T1003", "T1003"]})
    assert r.status_code in (200, 201), r.text
    fid = r.json()["id"]
    r = await client.put(f"/findings/{fid}", json={"attack_technique_ids": ["T1059", "T1059", "T1003"]})
    assert r.status_code == 200, r.text
    assert sorted((await client.get(f"/findings/{fid}")).json()["attack_technique_ids"]) == ["T1003", "T1059"]
    r = await client.post("/testcases", json={"engagement_id": eng.id, "title": "tc", "category": "Recon",
                                              "description": "d", "attack_technique_ids": ["T1110", "T1110"]})
    assert r.status_code in (200, 201), r.text
