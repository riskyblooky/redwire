"""Credential changes end sessions through one helper, in one order: API
tokens go in the same commit as the change, then the Redis cutoff. The
hand-rolled email and 2FA paths set the cutoff first, so a Redis failure
left the change committed and the rw_ tokens live."""

from __future__ import annotations

import uuid

from sqlalchemy import select


def _redis_down(monkeypatch):
    import auth.sessions
    monkeypatch.setattr(auth.sessions, "revoke_all_user_tokens", lambda user_id: False)


async def _token(db, user):
    from models.api_token import ApiToken
    tok = ApiToken(name="ci", token_hash=uuid.uuid4().hex * 2, token_prefix="rw_test", permission="ro", user_id=user.id)
    db.add(tok)
    await db.flush()
    return tok.id


async def _active(db, token_id):
    from models.api_token import ApiToken
    return (await db.execute(select(ApiToken.is_active).where(ApiToken.id == token_id)
                             .execution_options(populate_existing=True))).scalar_one()


async def test_email_change_ends_api_tokens_even_if_redis_fails(client, db_session, make_user, authenticate_as, monkeypatch):
    user = await make_user()
    tid = await _token(db_session, user)
    authenticate_as(user)
    _redis_down(monkeypatch)
    r = await client.put("/users/me", json={"email": f"new-{uuid.uuid4().hex[:6]}@redwire-dev.io",
                                            "current_password": "Sup3rSecret!pw"})
    assert r.status_code == 500
    assert await _active(db_session, tid) is False


async def test_password_change_ends_api_tokens_and_sessions(client, db_session, make_user, authenticate_as, monkeypatch):
    import auth.sessions
    calls = []
    monkeypatch.setattr(auth.sessions, "revoke_all_user_tokens", lambda uid: calls.append(uid) or True)
    user = await make_user()
    tid = await _token(db_session, user)
    authenticate_as(user)
    r = await client.put("/users/me/password", json={"old_password": "Sup3rSecret!pw", "new_password": "An0ther!Secret-pw"})
    assert r.status_code == 200, r.text
    assert calls == [user.id] and await _active(db_session, tid) is False


async def test_security_center_disable_leaves_api_tokens_to_is_active(client, db_session, make_user, authenticate_as, monkeypatch):
    import auth.sessions
    monkeypatch.setattr(auth.sessions, "revoke_all_user_tokens", lambda uid: True)
    target = await make_user()
    tid = await _token(db_session, target)
    authenticate_as(await make_user(role="admin"))
    r = await client.post(f"/admin/security/users/{target.id}/disable")
    assert r.status_code == 200, r.text
    assert await _active(db_session, tid) is True  # refused via user.is_active instead
