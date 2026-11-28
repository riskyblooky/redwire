"""API tokens end to end through the real auth path (Bearer JWT for the
interactive calls, Bearer ro_/rw_ token for the token's own use — not the
authenticate_as override): minting needs the password and an interactive
session, the raw token is shown once and never stored or listed, ro tokens
can't write, revocation and expiry take effect on the next request, a
deactivated owner's tokens stop working, and the admin endpoints are gated."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

PW = "Sup3rSecret!pw"


@pytest.fixture
def bearer(monkeypatch):
    import auth.dependencies as deps
    from auth.jwt import create_access_token
    monkeypatch.setattr(deps, "is_token_blacklisted", lambda _t: False)
    return lambda user: {"Authorization": f"Bearer {create_access_token({'sub': user.id})}"}


def _tok(raw):
    return {"Authorization": f"Bearer {raw}"}


async def _mint(client, headers, **body):
    body.setdefault("name", "ci")
    body.setdefault("password", PW)
    return await client.post("/api-tokens", headers=headers, json=body)


async def test_mint_needs_the_password(client, make_user, bearer):
    jwt = bearer(await make_user())
    assert (await _mint(client, jwt, password=None)).status_code in (400, 422)
    assert (await _mint(client, jwt, password="wrong")).status_code in (401, 403)
    r = await _mint(client, jwt)
    assert r.status_code == 201, r.text


async def test_raw_token_shown_once_and_only_its_hash_stored(client, db_session, make_user, bearer):
    from models.api_token import ApiToken
    user = await make_user()
    jwt = bearer(user)
    created = (await _mint(client, jwt, permission="rw")).json()
    raw = created["raw_token"]
    assert raw.startswith("rw_") and created["token_prefix"] == raw[:12]

    row = (await db_session.execute(select(ApiToken).where(ApiToken.id == created["id"]))).scalar_one()
    assert row.token_hash == hashlib.sha256(raw.encode()).hexdigest()
    assert raw not in {str(v) for v in vars(row).values()}, "the raw token is stored"

    listed = (await client.get("/api-tokens", headers=jwt)).json()
    assert [t["id"] for t in listed] == [created["id"]]
    assert raw not in str(listed) and "token_hash" not in listed[0] and "raw_token" not in listed[0]


async def test_ro_token_reads_but_cannot_write(client, make_user, bearer):
    user = await make_user()
    raw = (await _mint(client, bearer(user), permission="ro")).json()["raw_token"]
    me = await client.get("/auth/me", headers=_tok(raw))
    assert me.status_code == 200 and me.json()["id"] == user.id
    r = await client.post("/notifications/mark-all-read", headers=_tok(raw))
    assert r.status_code == 403 and "read-only" in r.text


async def test_rw_token_writes_but_cannot_mint(client, make_user, bearer):
    user = await make_user()
    raw = (await _mint(client, bearer(user), permission="rw")).json()["raw_token"]
    assert (await client.post("/notifications/mark-all-read", headers=_tok(raw))).status_code == 200
    r = await _mint(client, _tok(raw))
    assert r.status_code == 403 and "log in interactively" in r.text, "a token can't replace itself"


async def test_revoke_takes_effect_immediately_and_only_for_the_owner(client, make_user, bearer):
    alice, bob = await make_user(), await make_user()
    created = (await _mint(client, bearer(alice))).json()
    assert (await client.get("/auth/me", headers=_tok(created["raw_token"]))).status_code == 200

    assert (await client.delete(f"/api-tokens/{created['id']}", headers=bearer(bob))).status_code == 404
    assert (await client.get("/auth/me", headers=_tok(created["raw_token"]))).status_code == 200

    assert (await client.delete(f"/api-tokens/{created['id']}", headers=bearer(alice))).status_code == 204
    assert (await client.get("/auth/me", headers=_tok(created["raw_token"]))).status_code == 401


async def test_expired_and_unknown_tokens_are_refused(client, db_session, make_user, bearer):
    from sqlalchemy import update
    from models.api_token import ApiToken
    user = await make_user()
    soon = (datetime.utcnow() + timedelta(days=1)).isoformat()
    created = (await _mint(client, bearer(user), expires_at=soon)).json()
    assert (await client.get("/auth/me", headers=_tok(created["raw_token"]))).status_code == 200
    # Move the expiry into the past rather than waiting for it.
    await db_session.execute(update(ApiToken).where(ApiToken.id == created["id"])
                             .values(expires_at=datetime.utcnow() - timedelta(seconds=1)))
    await db_session.commit()
    assert (await client.get("/auth/me", headers=_tok(created["raw_token"]))).status_code == 401
    assert (await client.get("/auth/me", headers=_tok("rw_" + "0" * 40))).status_code == 401


async def test_tokens_stop_with_their_owner(client, db_session, make_user, bearer):
    user = await make_user()
    raw = (await _mint(client, bearer(user))).json()["raw_token"]
    user.is_active = False
    await db_session.commit()
    assert (await client.get("/auth/me", headers=_tok(raw))).status_code in (401, 403)


async def test_admin_endpoints_are_gated(client, make_user, bearer):
    admin, roa, op = await make_user(role="admin"), await make_user(role="read_only_admin"), await make_user()
    await _mint(client, bearer(op))

    assert (await client.get("/admin/api-tokens", headers=bearer(op))).status_code == 403
    listed = (await client.get("/admin/api-tokens", headers=bearer(roa))).json()
    mine = [t for t in listed if t["username"] == op.username]
    assert len(mine) == 1 and "raw_token" not in mine[0] and "token_hash" not in mine[0]

    body = {"name": "svc", "user_id": op.id, "permission": "ro"}
    assert (await client.post("/admin/api-tokens", headers=bearer(roa), json=body)).status_code == 403
    r = await client.post("/admin/api-tokens", headers=bearer(admin), json=body)
    assert r.status_code == 201, r.text
    svc = r.json()["raw_token"]
    me = await client.get("/auth/me", headers=_tok(svc))
    assert me.json()["id"] == op.id, "a service token acts as its target user"

    admin_rw = (await _mint(client, bearer(admin), permission="rw")).json()["raw_token"]
    assert (await client.post("/admin/api-tokens", headers=_tok(admin_rw), json=body)).status_code == 403, \
        "an admin's leaked token can't mint tokens for other users"
    assert (await client.post("/admin/api-tokens", headers=bearer(admin),
                              json={**body, "user_id": "00000000-0000-0000-0000-000000000000"})).status_code == 404
