"""The three evidence-upload endpoints share one pipeline: each returns
the uploader's name (only the test-case copy did), and a storage failure
is logged rather than echoed to the client."""

from __future__ import annotations

import uuid

import pytest


@pytest.fixture
def storage(monkeypatch):
    from utils.storage import storage_service
    state = {"fail": False}

    async def fake_upload(*a, **kw):
        if state["fail"]:
            raise RuntimeError("connect to minio-internal:9000 refused")
        return "ok"
    monkeypatch.setattr(storage_service, "upload_file", fake_upload)
    return state


async def _targets(db, owner):
    from models.engagement import Engagement
    from models.finding import Finding
    from models.testcase import TestCase
    eng = Engagement(id=str(uuid.uuid4()), name=f"E-{uuid.uuid4().hex[:6]}", client_name="ACME",
                     engagement_type="external_pentest", created_by=owner.id)
    db.add(eng)
    await db.flush()
    f = Finding(id=str(uuid.uuid4()), engagement_id=eng.id, title="F", description="d", severity="HIGH",
                status="OPEN", created_by=owner.id)
    t = TestCase(id=str(uuid.uuid4()), engagement_id=eng.id, title="T", category="Recon", description="d", created_by=owner.id)
    db.add_all([f, t])
    await db.flush()
    return [f"/engagements/{eng.id}/evidence", f"/findings/{f.id}/evidence", f"/testcases/{t.id}/evidence"]


async def test_every_upload_returns_the_uploader(client, db_session, make_user, authenticate_as, storage):
    admin = await make_user(role="admin", full_name="Ada Admin")
    authenticate_as(admin)
    for url in await _targets(db_session, admin):
        r = await client.post(url, files={"file": ("shot.png", b"\x89PNG data", "image/png")})
        assert r.status_code == 200, (url, r.text)
        body = r.json()
        assert body["created_by_full_name"] == "Ada Admin" and body["mime_type"] == "image/png", url


async def test_storage_failure_is_not_echoed(client, db_session, make_user, authenticate_as, storage):
    admin = await make_user(role="admin")
    authenticate_as(admin)
    storage["fail"] = True
    for url in await _targets(db_session, admin):
        r = await client.post(url, files={"file": ("a.txt", b"x", "text/plain")})
        assert r.status_code == 500, url
        assert "minio" not in r.text, url
