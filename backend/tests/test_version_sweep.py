"""Deleting a versioned entity (or its engagement) deletes its version history."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select

from models.asset import Asset
from models.note import Note
from models.testcase import TestCase
from models.version_history import VersionHistory
from tests.test_authz_boundaries import _make_engagement, _make_finding


def _u() -> str:
    return str(uuid.uuid4())


async def _version(db, entity_type, entity_id):
    db.add(VersionHistory(id=_u(), entity_type=entity_type, entity_id=entity_id, version=1,
                          snapshot={"x": 1}, changed_fields=["x"]))
    await db.flush()


async def _versions(db, entity_id) -> int:
    return (await db.execute(select(func.count()).select_from(VersionHistory)
                             .where(VersionHistory.entity_id == entity_id))).scalar_one()


async def _entities(db, eng):
    f = await _make_finding(db, eng)
    tc = TestCase(id=_u(), engagement_id=eng.id, title="t", category="web", description="d")
    a = Asset(id=_u(), engagement_id=eng.id, name="h", asset_type="Server", identifier=f"10.9.{uuid.uuid4().int % 250}.1")
    n = Note(id=_u(), engagement_id=eng.id, title="n", content="c")
    db.add_all([tc, a, n])
    await db.flush()
    ents = {"finding": f.id, "testcase": tc.id, "asset": a.id, "note": n.id}
    for t, i in ents.items():
        await _version(db, t, i)
    return ents


@pytest.mark.parametrize("entity_type,path", [
    ("finding", "/findings/{id}"),
    ("testcase", "/testcases/{id}"),
    ("asset", "/assets/{id}"),
    ("note", "/notes/{id}"),
])
async def test_deleting_an_entity_deletes_its_versions(client, db_session, make_user, authenticate_as, entity_type, path):
    admin = await make_user(role="admin")
    authenticate_as(admin)
    eng = await _make_engagement(db_session)
    ents = await _entities(db_session, eng)
    eid = ents[entity_type]

    r = await client.delete(path.format(id=eid))
    assert r.status_code in (200, 204), r.text
    assert await _versions(db_session, eid) == 0
    # The other entities' history is untouched.
    for t, other in ents.items():
        if t != entity_type:
            assert await _versions(db_session, other) == 1


async def test_deleting_an_engagement_deletes_its_entities_versions(client, db_session, make_user, authenticate_as):
    admin = await make_user(role="admin")
    authenticate_as(admin)
    eng = await _make_engagement(db_session)
    ents = await _entities(db_session, eng)
    other_eng = await _make_engagement(db_session)
    keep = (await _make_finding(db_session, other_eng)).id
    await _version(db_session, "finding", keep)

    r = await client.delete(f"/engagements/{eng.id}")
    assert r.status_code == 204, r.text
    for eid in ents.values():
        assert await _versions(db_session, eid) == 0
    assert await _versions(db_session, keep) == 1
