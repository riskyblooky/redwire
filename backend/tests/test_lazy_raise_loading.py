"""Core relationships are lazy="raise" and each response loads its own links
(models/loaders.py). These cover the write paths that replace a collection
on an existing row, and the shape of what one finding load pulls in."""

from __future__ import annotations

import uuid

from sqlalchemy import event, select

from models.asset import Asset
from models.asset_port import AssetPort
from models.finding import Finding, Severity
from models.testcase import TestCase


def u():
    return str(uuid.uuid4())


async def test_testcase_update_replaces_techniques_and_tags(client, db_session, make_user, authenticate_as):
    from tests.test_authz_boundaries import _make_engagement
    eng = await _make_engagement(db_session)
    tc = TestCase(id=u(), engagement_id=eng.id, title="tc", category="Web", description="d")
    db_session.add(tc)
    await db_session.flush()
    tc_id = tc.id
    db_session.expunge_all()
    authenticate_as(await make_user(role="admin"))
    r = await client.put(f"/testcases/{tc_id}", json={"attack_technique_ids": ["T1003", "T1059"], "tag_ids": []})
    assert r.status_code == 200, r.text
    # (the PUT response doesn't carry technique ids; GET fills them in)
    assert sorted((await client.get(f"/testcases/{tc_id}")).json()["attack_technique_ids"]) == ["T1003", "T1059"]
    r = await client.put(f"/testcases/{tc_id}", json={"attack_technique_ids": ["T1110"]})
    assert r.status_code == 200, r.text
    assert (await client.get(f"/testcases/{tc_id}")).json()["attack_technique_ids"] == ["T1110"]


async def test_create_returns_links_for_each_resource(client, db_session, make_user, authenticate_as):
    from tests.test_authz_boundaries import _make_engagement
    eng = await _make_engagement(db_session)
    eid = eng.id
    db_session.expunge_all()
    authenticate_as(await make_user(role="admin"))
    r = await client.post("/vault", json={"engagement_id": eid, "name": "v", "item_type": "Credential", "username": "u", "password": "p"})
    assert r.status_code in (200, 201), r.text
    assert r.json()["findings"] == [] and r.json()["assets"] == []
    r = await client.post("/cleanup-artifacts", json={"engagement_id": eid, "title": "c", "artifact_type": "FILE"})
    assert r.status_code in (200, 201), r.text
    aid = r.json()["id"]
    r = await client.patch(f"/cleanup-artifacts/{aid}", json={"title": "c2"})
    assert r.status_code == 200, r.text
    assert r.json()["findings"] == []
    r = await client.post(f"/engagements/{eid}/notes", json={"title": "n", "content": "x"})
    assert r.status_code in (200, 201), r.text


async def test_one_finding_does_not_pull_in_asset_ports(db_session):
    """The selectin web used to load every linked asset's ports (and their
    findings, test cases, vault items...) just to load one finding."""
    from models.loaders import options
    from models.associations import FindingAsset
    from tests.test_authz_boundaries import _make_engagement
    eng = await _make_engagement(db_session)
    a = Asset(id=u(), engagement_id=eng.id, name="a", asset_type="Server", identifier="10.9.9.9")
    f = Finding(id=u(), engagement_id=eng.id, title="t", description="d", severity=Severity.HIGH)
    db_session.add_all([a, f])
    await db_session.flush()
    db_session.add_all([AssetPort(id=u(), asset_id=a.id, port_number=p, protocol="TCP", state="OPEN") for p in (22, 80, 443)])
    await db_session.execute(FindingAsset.__table__.insert().values(finding_id=f.id, asset_id=a.id))
    await db_session.flush()
    fid = f.id
    db_session.expunge_all()
    got = (await db_session.execute(select(Finding).where(Finding.id == fid).options(*options("FINDING")))).scalar_one()
    assert [x.id for x in got.assets] == [a.id]
    loaded = {type(o).__name__ for o in db_session.identity_map.values()}
    assert "AssetPort" not in loaded
