"""Reset links and 2FA-pending tokens are single use, and password changes
end API tokens as well as sessions."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from auth import jwt as authjwt


async def test_used_reset_link_is_rejected(client, make_user):
    user = await make_user()
    tok = authjwt.create_access_token({"sub": user.id, "type": "password_reset"})
    assert authjwt.blacklist_token(tok)
    r = await client.post("/auth/reset-password", json={"token": tok, "new_password": "An0ther!Passw0rd"})
    assert r.status_code == 400


async def test_used_2fa_pending_token_is_rejected(client, make_user):
    user = await make_user()
    tok = authjwt.create_access_token({"sub": user.id, "role": "operator", "2fa_pending": True})
    assert authjwt.blacklist_token(tok)
    r = await client.post("/auth/verify-2fa", json={"code": "123456"}, headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 401 and r.json()["detail"] == "Invalid or expired token"


async def test_password_change_deactivates_api_tokens(client, db_session, make_user, authenticate_as):
    from models.api_token import ApiToken
    user = await make_user(password="Old!Passw0rd1")
    db_session.add(ApiToken(name="ci", token_hash=uuid.uuid4().hex, token_prefix="rw_test", permission="rw",
                            user_id=user.id))
    await db_session.flush()
    authenticate_as(user)
    r = await client.put("/users/me/password", json={"old_password": "Old!Passw0rd1", "new_password": "New!Passw0rd2"})
    assert r.status_code == 200
    tokens = (await db_session.execute(select(ApiToken).where(ApiToken.user_id == user.id)
                                       .execution_options(populate_existing=True))).scalars().all()
    assert tokens and not any(t.is_active for t in tokens)
