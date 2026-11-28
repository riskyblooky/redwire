"""/users self-service and directory endpoints: the self-update only applies
its allowlist (no self-granted role, re-activation, groups or photo path),
an email change needs the password, a password or email change ends the
user's API tokens, the team picker exposes summary fields only, and another
user's full profile needs VIEW_ALL_USERS."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from tests.test_api_tokens import bearer  # noqa: F401  (fixture: real JWT auth path)

PW = "Sup3rSecret!pw"


async def _reload(db, user):
    from models.user import User
    db.expunge_all()
    return (await db.execute(select(User).where(User.id == user.id))).scalar_one()


async def _api_token(db, user):
    from models.api_token import ApiToken
    t = ApiToken(id=str(uuid.uuid4()), user_id=user.id, name="t", token_hash=uuid.uuid4().hex,
                 token_prefix="rw_xxxxxxxxx", permission="rw", is_active=True)
    db.add(t)
    await db.commit()
    return t.id


async def _token_active(db, token_id):
    from models.api_token import ApiToken
    db.expunge_all()
    return (await db.execute(select(ApiToken.is_active).where(ApiToken.id == token_id))).scalar_one()


# The write tests authenticate through the real JWT path, which loads the
# user (with groups) in the request's session as production does. The test
# shares that session, so clear its identity map first: a user left there by
# make_user has groups unloaded, and selectinload won't refill it.
async def test_self_update_ignores_privileged_fields(client, db_session, make_user, bearer):
    from models.group import Group
    op = await make_user()
    g = Group(id=str(uuid.uuid4()), name=f"g-{uuid.uuid4().hex[:6]}")
    db_session.add(g)
    await db_session.commit()
    db_session.expunge_all()
    r = await client.put("/users/me", headers=bearer(op), json={
        "full_name": "New Name", "role": "admin", "is_active": False, "group_ids": [g.id],
        "profile_photo": "../../etc/passwd", "theme_palette": "light"})
    assert r.status_code == 200, r.text
    me = await _reload(db_session, op)
    assert (me.full_name, me.role.value, me.is_active, me.profile_photo, me.theme_palette) == (
        "New Name", "operator", True, None, "light")
    from models.group import user_groups
    assert (await db_session.execute(select(user_groups).where(user_groups.c.user_id == op.id))).first() is None


@pytest.mark.parametrize("body", [{"theme_palette": "neon"}, {"theme_preference": "x"}, {"theme_accent_custom": "red"}])
async def test_self_update_validates_theme(client, make_user, authenticate_as, body):
    authenticate_as(await make_user())
    assert (await client.put("/users/me", json=body)).status_code in (400, 422)


async def test_email_change_needs_password_and_ends_tokens(client, db_session, make_user, bearer):
    op = await make_user()
    token = await _api_token(db_session, op)
    jwt = bearer(op)
    new = f"new-{uuid.uuid4().hex[:6]}@example.org"
    assert (await client.put("/users/me", headers=jwt, json={"email": new})).status_code == 401
    assert (await client.put("/users/me", headers=jwt, json={"email": new, "current_password": "wrong"})).status_code == 401
    assert (await _reload(db_session, op)).email != new and await _token_active(db_session, token)
    db_session.expunge_all()

    r = await client.put("/users/me", headers=jwt, json={"email": new, "current_password": PW})
    assert r.status_code == 200, r.text
    assert (await _reload(db_session, op)).email == new
    assert not await _token_active(db_session, token), "an email change must end API tokens"


async def test_password_change(client, db_session, make_user, bearer):
    from auth.password import verify_password
    op = await make_user()
    token = await _api_token(db_session, op)
    jwt = bearer(op)
    bad = await client.put("/users/me/password", headers=jwt, json={"old_password": "nope", "new_password": "An0ther-good-one"})
    assert bad.status_code == 400 and await _token_active(db_session, token)
    assert (await client.put("/users/me/password", headers=jwt,
                             json={"old_password": PW, "new_password": "short"})).status_code == 422

    r = await client.put("/users/me/password", headers=jwt, json={"old_password": PW, "new_password": "An0ther-good-one"})
    assert r.status_code == 200, r.text
    assert verify_password("An0ther-good-one", (await _reload(db_session, op)).hashed_password)
    assert not await _token_active(db_session, token)


async def test_team_picker_is_summary_only_and_active_only(client, db_session, make_user, authenticate_as):
    gone = await make_user()
    gone.is_active = False
    await db_session.commit()
    authenticate_as(await make_user())
    rows = (await client.get("/users", params={"limit": 500})).json()
    assert rows and all(set(r) <= {"id", "username", "email", "full_name", "profile_photo", "role"} for r in rows)
    assert gone.id not in {r["id"] for r in rows}


async def test_full_profile_needs_view_all_users(client, db_session, make_user, authenticate_as):
    from models.group import Group, user_groups
    from models.permission import GroupPermissions, Permission
    target, op, roa = await make_user(), await make_user(), await make_user(role="read_only_admin")
    granted = await make_user()
    g = Group(id=str(uuid.uuid4()), name=f"dir-{uuid.uuid4().hex[:6]}")
    db_session.add(g)
    await db_session.flush()
    db_session.add(GroupPermissions(group_id=g.id, permissions=[Permission.VIEW_ALL_USERS.value]))
    await db_session.execute(user_groups.insert().values(user_id=granted.id, group_id=g.id))
    await db_session.commit()

    authenticate_as(op)
    assert (await client.get(f"/users/{target.id}")).status_code == 403
    assert (await client.get(f"/users/{op.id}")).status_code == 200, "your own profile"
    for who in (roa, granted):
        authenticate_as(who)
        r = await client.get(f"/users/{target.id}")
        assert r.status_code == 200 and r.json()["id"] == target.id
        assert "hashed_password" not in r.json() and "totp_secret" not in r.json()
