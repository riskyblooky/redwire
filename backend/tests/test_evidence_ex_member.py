"""GHSA-7x2f-ff7r-h388 #1: a creator who has been removed from the
engagement can't keep adding evidence to their finding / test case;
a creator who is still a member can."""

from __future__ import annotations

import uuid

import pytest

from tests.test_authz_boundaries import _assign, _make_engagement, _make_engagement_role, _make_finding


@pytest.fixture(autouse=True)
def _no_minio(monkeypatch):
    from utils.storage import storage_service

    async def fake_upload(content, name, content_type=None):
        return name
    monkeypatch.setattr(storage_service, "upload_file", fake_upload)


async def _testcase(db, eng, creator):
    from models.testcase import TestCase
    tc = TestCase(id=str(uuid.uuid4()), engagement_id=eng.id, title="t", category="c", description="d",
                  created_by=creator.id)
    db.add(tc)
    await db.flush()
    return tc


async def _upload(client, path):
    return await client.post(path, files={"file": ("a.txt", b"hello", "text/plain")})


@pytest.mark.parametrize("kind", ["finding", "testcase"])
async def test_ex_member_creator_blocked(kind, client, db_session, make_user, authenticate_as):
    eng = await _make_engagement(db_session)
    creator = await make_user(role="operator")
    item = (await _make_finding(db_session, eng, created_by=creator.id) if kind == "finding"
            else await _testcase(db_session, eng, creator))
    authenticate_as(creator)
    r = await _upload(client, f"/{kind}s/{item.id}/evidence")
    assert r.status_code == 403 and "no longer a member" in r.json()["detail"]


@pytest.mark.parametrize("kind", ["finding", "testcase"])
async def test_member_creator_allowed(kind, client, db_session, make_user, authenticate_as):
    eng = await _make_engagement(db_session)
    creator = await make_user(role="operator")
    await _assign(db_session, creator, eng, await _make_engagement_role(db_session, ["engagement_view"]))
    item = (await _make_finding(db_session, eng, created_by=creator.id) if kind == "finding"
            else await _testcase(db_session, eng, creator))
    authenticate_as(creator)
    r = await _upload(client, f"/{kind}s/{item.id}/evidence")
    assert r.status_code == 200, r.text
