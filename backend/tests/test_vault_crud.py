"""Vault CRUD over HTTP. Secrets are encrypted at rest, never in list / get
responses (only has_* flags), and come back only from /reveal, which needs
vault_view and is audited. Editing or deleting another member's item needs
the *_ANY permission; a member without vault_view sees nothing."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import select

import pytest

from tests.test_authz_boundaries import _assign, _make_engagement, _make_engagement_role

SECRET = "Hunter2!-not-in-any-response"


@pytest.fixture
async def team(db_session, make_user):
    eng = await _make_engagement(db_session)
    own = ["engagement_view", "vault_view", "vault_create", "vault_edit", "vault_delete"]
    member_role = await _make_engagement_role(db_session, own)
    lead_role = await _make_engagement_role(db_session, own + ["vault_edit_any", "vault_delete_any"])
    blind_role = await _make_engagement_role(db_session, ["engagement_view", "finding_view"])
    alice, bob, lead, blind = await make_user(), await make_user(), await make_user(), await make_user()
    for u, r in ((alice, member_role), (bob, member_role), (lead, lead_role), (blind, blind_role)):
        await _assign(db_session, u, eng, r)
    await db_session.commit()
    return eng, alice, bob, lead, blind


async def _create(client, eng, **over):
    body = {"engagement_id": eng.id, "name": "dc admin", "item_type": "Credential",
            "username": "CORP\\admin", "password": SECRET, "note": "from lsass"}
    body.update(over)
    r = await client.post("/vault", json=body)
    assert r.status_code == 201, r.text
    return r.json()


async def test_secret_is_encrypted_at_rest_and_only_revealed(client, db_session, authenticate_as, team):
    from models.discussion import ActivityLog
    eng, alice, *_ = team
    authenticate_as(alice)
    item = await _create(client, eng)
    assert SECRET not in str(item) and item["has_password"] is True

    raw = (await db_session.execute(sa.text("SELECT username, password, note FROM vault_items WHERE id = :i"),
                                    {"i": item["id"]})).one()
    assert SECRET not in "".join(map(str, raw)) and "lsass" not in str(raw[2]), "stored in plaintext"

    listed = (await client.get("/vault", params={"engagement_id": eng.id})).json()
    assert [i["id"] for i in listed] == [item["id"]] and SECRET not in str(listed)
    assert SECRET not in (await client.get(f"/vault/{item['id']}")).text

    revealed = (await client.get(f"/vault/{item['id']}/reveal")).json()
    assert (revealed["username"], revealed["password"], revealed["note"]) == ("CORP\\admin", SECRET, "from lsass")
    db_session.expunge_all()
    logged = (await db_session.execute(select(ActivityLog.action).where(
        ActivityLog.resource_id == item["id"], ActivityLog.user_id == alice.id))).scalars().all()
    assert "accessed_vault_secret" in logged


async def test_without_vault_view_nothing_is_visible(client, authenticate_as, team):
    eng, alice, bob, lead, blind = team
    authenticate_as(alice)
    item = await _create(client, eng)
    authenticate_as(blind)
    assert (await client.get("/vault", params={"engagement_id": eng.id})).status_code == 403
    for url in (f"/vault/{item['id']}", f"/vault/{item['id']}/reveal"):
        assert (await client.get(url)).status_code == 403, url
    assert (await client.post("/vault", json={"engagement_id": eng.id, "name": "x", "item_type": "Credential"})).status_code == 403


async def test_edit_and_delete_others_need_the_any_permission(client, db_session, authenticate_as, team):
    from models.vault import VaultItem
    eng, alice, bob, lead, blind = team
    authenticate_as(alice)
    item = await _create(client, eng)

    authenticate_as(bob)  # same role as alice, not the owner
    assert (await client.patch(f"/vault/{item['id']}", json={"password": "bob-was-here"})).status_code == 403
    assert (await client.delete(f"/vault/{item['id']}")).status_code == 403

    authenticate_as(alice)  # the owner, with vault_edit
    r = await client.patch(f"/vault/{item['id']}", json={"password": "rotated-1"})
    assert r.status_code == 200 and "rotated-1" not in r.text
    assert (await client.get(f"/vault/{item['id']}/reveal")).json()["password"] == "rotated-1"

    authenticate_as(lead)  # vault_edit_any / vault_delete_any
    assert (await client.patch(f"/vault/{item['id']}", json={"name": "renamed"})).json()["name"] == "renamed"
    assert (await client.get(f"/vault/{item['id']}/reveal")).json()["password"] == "rotated-1", \
        "a metadata edit must not touch the secret"
    assert (await client.delete(f"/vault/{item['id']}")).status_code == 204
    db_session.expunge_all()
    assert (await db_session.execute(select(VaultItem).where(VaultItem.id == item["id"]))).first() is None


async def test_list_is_scoped_to_the_engagement(client, db_session, authenticate_as, team):
    eng, alice, *_ = team
    other = await _make_engagement(db_session)
    await db_session.commit()
    authenticate_as(alice)
    await _create(client, eng)
    assert (await client.get("/vault", params={"engagement_id": other.id})).status_code == 403
    assert (await client.post("/vault", json={"engagement_id": other.id, "name": "x", "item_type": "Credential"})).status_code == 403
