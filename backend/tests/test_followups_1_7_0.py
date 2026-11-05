"""1.7.0 small follow-ups: library-scope markdown images, and the
dashboard:global feed reaching admins / VIEW_ALL_ENGAGEMENTS holders."""

from __future__ import annotations

import uuid

import pytest

from models.engagement import Engagement

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


@pytest.fixture
def mem_storage(monkeypatch):
    import routers.markdown_images as mi
    store: dict[str, bytes] = {}

    async def upload_file(body, key, content_type):
        store[key] = body

    async def download_file(key):
        return store[key]
    monkeypatch.setattr(mi.storage_service, "upload_file", upload_file)
    monkeypatch.setattr(mi.storage_service, "download_file", download_file)
    return store


async def _engagement(db, owner):
    eng = Engagement(id=str(uuid.uuid4()), name="Img Test", client_name="ACME",
                     engagement_type="external_pentest", created_by=owner.id)
    db.add(eng)
    await db.flush()
    return eng


async def test_library_image_upload_and_fetch_by_any_user(client, make_user, authenticate_as, mem_storage):
    author = await make_user(role="operator", username=f"lib_a_{uuid.uuid4().hex[:6]}")
    authenticate_as(author)
    up = await client.post("/markdown-images", data={"scope": "library"},
                           files={"file": ("shot.png", PNG, "image/png")})
    assert up.status_code == 201, up.text
    image_id = up.json()["id"]
    assert any(k.startswith("markdown/library/") for k in mem_storage)

    reader = await make_user(role="operator", username=f"lib_r_{uuid.uuid4().hex[:6]}")
    authenticate_as(reader)
    got = await client.get(f"/markdown-images/{image_id}")
    assert got.status_code == 200 and got.content == PNG


async def test_image_scope_validation(client, db_session, make_user, authenticate_as, mem_storage):
    admin = await make_user(role="admin", username=f"lib_ad_{uuid.uuid4().hex[:6]}")
    authenticate_as(admin)
    eng = await _engagement(db_session, admin)
    f = {"file": ("x.png", PNG, "image/png")}
    assert (await client.post("/markdown-images", files=f)).status_code == 400  # no engagement, no scope
    assert (await client.post("/markdown-images", data={"scope": "bogus"}, files=f)).status_code == 400
    assert (await client.post("/markdown-images", data={"scope": "library", "engagement_id": eng.id},
                              files=f)).status_code == 400


async def test_engagement_image_still_gated(client, db_session, make_user, authenticate_as, mem_storage):
    admin = await make_user(role="admin", username=f"eimg_ad_{uuid.uuid4().hex[:6]}")
    authenticate_as(admin)
    eng = await _engagement(db_session, admin)
    up = await client.post("/markdown-images", data={"engagement_id": eng.id},
                           files={"file": ("x.png", PNG, "image/png")})
    assert up.status_code == 201, up.text

    outsider = await make_user(role="operator", username=f"eimg_op_{uuid.uuid4().hex[:6]}")
    authenticate_as(outsider)
    assert (await client.get(f"/markdown-images/{up.json()['id']}")).status_code == 403


async def test_can_view_engagement_three_tiers(db_session, make_user, monkeypatch):
    import auth.permissions as perms
    from auth.rbac import can_view_engagement

    admin = await make_user(role="admin", username=f"cv_ad_{uuid.uuid4().hex[:6]}")
    lead = await make_user(role="operator", username=f"cv_va_{uuid.uuid4().hex[:6]}")
    plain = await make_user(role="operator", username=f"cv_op_{uuid.uuid4().hex[:6]}")
    eng = await _engagement(db_session, admin)

    async def _global(user, permission, db):
        return user.id == lead.id
    monkeypatch.setattr(perms, "has_global_permission", _global)

    assert await can_view_engagement(admin.id, eng.id, db_session) is True
    assert await can_view_engagement(lead.id, eng.id, db_session) is True   # VIEW_ALL_ENGAGEMENTS
    assert await can_view_engagement(plain.id, eng.id, db_session) is False

    admin.is_active = False
    await db_session.flush()
    assert await can_view_engagement(admin.id, eng.id, db_session) is False
