"""GHSA-7x2f-ff7r-h388 cluster B — authorization / scoping gates.

Five sub-issues shipped:

  #1  (CWE-863) `is_creator` short-circuit lets ex-members write.
      Fix: new `is_engagement_member` helper gates the creator bypass
      at three router sites.
  #5  (CWE-602) AI chatbot mode selectable client-side, `chatbot_enabled`
      server flag not enforced. Fix: `/chat` refuses when
      `field_context.resourceType == "chatbot"` and the admin has
      chatbot_enabled=false.
  #6  (CWE-862) Spray-commit auto-creates Assets under VAULT_CREATE
      gate; ASSET_CREATE bypass. Fix: additional ASSET_CREATE check
      when `create_missing_assets=true`.
  #7  (CWE-200) `GET /plugins/` returned admin-configured manifest to
      any authenticated user. Fix: admin-only via
      `require_roles(ADMIN_ROLES)`.
  #11 (CWE-178) Admin-create email path used raw `str`; self-register
      used `EmailStr`. Fix: unify on EmailStr + `.strip().lower()`
      canonicalisation.

Bigger issues (#8 enum bypass on import, #12 version-history race,
#14 runbook-apply commit ordering) are deferred to the follow-up
review — captured in the todo.
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from tests.test_authz_boundaries import _assign, _make_engagement, _make_engagement_role


# ── Issue 1: ex-member creator can't edit or resolve their thread ────
# (evidence on a creator's finding / test case: test_evidence_ex_member.py)


async def _thread(db, eng, creator):
    from models.discussion import Thread
    t = Thread(id=str(uuid.uuid4()), engagement_id=eng.id, resource_type="engagement",
               title="t", created_by=creator.id)
    db.add(t)
    await db.flush()
    return t


@pytest.mark.parametrize("method, suffix, body", [
    ("put", "", {"title": "edited"}),
    ("put", "/resolve", None),
])
async def test_ex_member_creator_cannot_change_thread(method, suffix, body, client, db_session, make_user, authenticate_as):
    eng = await _make_engagement(db_session)
    creator = await make_user(role="operator")
    thread = await _thread(db_session, eng, creator)
    authenticate_as(creator)

    r = await client.request(method.upper(), f"/discussions/threads/{thread.id}{suffix}", json=body)

    assert r.status_code == 403
    assert "no longer a member" in r.json()["detail"]


async def test_member_creator_can_resolve_thread(client, db_session, make_user, authenticate_as):
    eng = await _make_engagement(db_session)
    creator = await make_user(role="operator")
    await _assign(db_session, creator, eng, await _make_engagement_role(db_session, ["engagement_view", "discussion_view"]))
    thread = await _thread(db_session, eng, creator)
    authenticate_as(creator)

    r = await client.put(f"/discussions/threads/{thread.id}/resolve")

    assert r.status_code == 200, r.text
    assert r.json()["is_resolved"] is True


# ── Issue 5: chatbot_enabled enforced server-side ────────────────────


async def test_chatbot_mode_refused_when_disabled(client, make_user, authenticate_as, monkeypatch):
    from routers import ai

    async def _settings(db):
        return {"ai_enabled": "true", "ai_api_key": "k", "chatbot_enabled": "false"}
    monkeypatch.setattr(ai, "_get_ai_settings", _settings)

    authenticate_as(await make_user(role="operator"))
    r = await client.post("/ai/chat", json={
        "messages": [{"role": "user", "content": "hi"}],
        "field_context": {"resourceType": "chatbot"},
    })

    assert r.status_code == 403
    assert r.json()["detail"] == "AI chatbot is disabled on this instance."


# ── Issue 6: spray auto-inventory needs ASSET_CREATE ─────────────────


def _spray(eng_id, create_missing_assets):
    return {
        "engagement_id": eng_id, "name": "spray", "protocol": "smb",
        "create_missing_assets": create_missing_assets,
        "results": [{"username": "bob", "result": "failed", "target_host": "10.1.2.3"}],
    }


async def test_spray_auto_inventory_needs_asset_create(client, db_session, make_user, authenticate_as):
    from sqlalchemy import func, select
    from models.asset import Asset

    eng = await _make_engagement(db_session)
    op = await make_user(role="operator")
    await _assign(db_session, op, eng, await _make_engagement_role(db_session, ["engagement_view", "vault_create"]))
    authenticate_as(op)

    r = await client.post("/spray/commit", json=_spray(eng.id, True))
    assert r.status_code == 403
    assert "asset_create" in r.json()["detail"]

    # Without the auto-inventory the same user may commit, and no asset appears.
    r = await client.post("/spray/commit", json=_spray(eng.id, False))
    assert r.status_code == 201, r.text
    n = (await db_session.execute(select(func.count()).select_from(Asset).where(Asset.engagement_id == eng.id))).scalar()
    assert n == 0


# ── Issue 7: plugin list and details are admin-only ──────────────────


@pytest.mark.parametrize("path", ["/plugins/", "/plugins/some-plugin"])
async def test_plugin_endpoints_refuse_non_admins(path, client, make_user, authenticate_as):
    authenticate_as(await make_user(role="operator"))
    assert (await client.get(path)).status_code == 403


async def test_plugin_list_open_to_admins(client, make_user, authenticate_as):
    authenticate_as(await make_user(role="admin"))
    assert (await client.get("/plugins/")).status_code == 200


# ── Issue 11: email canonicalization symmetry ────────────────────────


class TestEmailNormalizationParity:
    """Both admin-create and self-register must produce the same
    canonical email so uniqueness checks match under case variation."""

    def test_self_register_lowercases_email(self):
        from schemas.user import UserCreate
        u = UserCreate(username="alice", email="Foo@BAR.com", password="passw0rd")
        assert u.email == "foo@bar.com"

    def test_self_register_strips_email(self):
        from schemas.user import UserCreate
        u = UserCreate(username="alice", email="  foo@bar.com  ", password="passw0rd")
        assert u.email == "foo@bar.com"

    def test_admin_create_lowercases_email(self):
        from routers.admin import AdminUserCreate
        u = AdminUserCreate(username="alice", email="Foo@BAR.com", password="passw0rd")
        assert u.email == "foo@bar.com"

    def test_admin_create_uses_emailstr_validation(self):
        from routers.admin import AdminUserCreate
        with pytest.raises(ValidationError):
            AdminUserCreate(username="alice", email="not-an-email", password="passw0rd")
