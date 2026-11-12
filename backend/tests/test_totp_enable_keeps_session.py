"""Enabling 2FA revokes every session, the caller's included. The caller
must get a fresh one back, or the profile page is sent to login before it
can show the one-time recovery codes."""

from __future__ import annotations

import pyotp
import pytest

from auth.jwt import create_access_token


@pytest.fixture
def bearer(monkeypatch):
    import auth.dependencies as deps
    monkeypatch.setattr(deps, "is_token_blacklisted", lambda _t: False)
    return lambda user: {"Authorization": f"Bearer {create_access_token({'sub': user.id})}"}


async def test_enable_2fa_returns_working_session(client, make_user, bearer):
    user = await make_user()
    old = bearer(user)
    setup = await client.post("/auth/totp/setup", headers=old, json={"password": "Sup3rSecret!pw"})
    assert setup.status_code == 200, setup.text
    r = await client.post("/auth/totp/verify-setup", headers=old,
                          json={"code": pyotp.TOTP(setup.json()["secret"]).now()})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["recovery_codes"]) > 0 and body["access_token"]
    assert "refresh_token=" in r.headers.get("set-cookie", "")

    fresh = {"Authorization": f"Bearer {body['access_token']}"}
    me = await client.get("/auth/me", headers=fresh)
    assert me.status_code == 200 and me.json()["totp_enabled"] is True
