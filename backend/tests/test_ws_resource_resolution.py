"""The presence socket resolves ``/ws/{resource_type}/{resource_id}`` to
(exists, owning engagement) for every type it serves; the engagement is what
its view gate checks, so a wrong owner would open another engagement's feed."""

from __future__ import annotations

import uuid

import pytest

from tests.test_authz_boundaries import _make_engagement, _make_finding


@pytest.fixture
async def rows(db_session, make_user):
    from models.asset import Asset
    from models.evidence import Evidence
    from models.note import Note
    from models.testcase import TestCase
    eng = await _make_engagement(db_session)
    f = await _make_finding(db_session, eng)
    ids = {"asset": str(uuid.uuid4()), "testcase": str(uuid.uuid4()), "note": str(uuid.uuid4()),
           "evidence": str(uuid.uuid4())}
    db_session.add_all([
        Asset(id=ids["asset"], engagement_id=eng.id, name="h", identifier="h.corp", asset_type="host"),
        TestCase(id=ids["testcase"], engagement_id=eng.id, title="t", category="Recon", description="d"),
        Note(id=ids["note"], engagement_id=eng.id, title="n", content="c"),
    ])
    await db_session.flush()
    db_session.add(Evidence(id=ids["evidence"], finding_id=f.id, engagement_id=eng.id,
                            filename="e.png", original_filename="e.png", file_path="x/e.png",
                            file_size=1, mime_type="image/png"))
    user = await make_user()
    await db_session.flush()
    return eng, f, ids, user


async def test_every_type_resolves_to_its_engagement(db_session, rows):
    from routers.websocket import _resolve_presence_resource as resolve
    eng, f, ids, user = rows
    for rtype, rid in [("engagement", eng.id), ("report", eng.id), ("finding", f.id), *ids.items()]:
        assert await resolve(rtype, rid, db_session) == (True, eng.id), rtype
        assert await resolve(rtype, str(uuid.uuid4()), db_session) == (False, None), rtype

    assert await resolve("dashboard", "global", db_session) == (True, None)
    assert await resolve("dashboard", eng.id, db_session) == (False, None)
    assert await resolve("user", user.id, db_session) == (True, None)
    assert await resolve("user", str(uuid.uuid4()), db_session) == (False, None)
    assert await resolve("vault", str(uuid.uuid4()), db_session) == (False, None), "unknown type"
