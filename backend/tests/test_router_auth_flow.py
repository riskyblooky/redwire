"""End-to-end tests for the local-auth surface of ``routers/auth.py``.

Drives the real handlers through the httpx ``client`` fixture (get_db is
overridden to the rolled-back test session). Accounts are created with
``make_user`` so the stored bcrypt hash matches the plaintext we log in
with, exercising the genuine ``verify_password`` path.

Scope covered here:
  * POST /auth/login — correct creds → access token (+ refresh cookie);
    wrong password → 401; unknown user → 401 (constant-time branch);
    inactive account → 403; 2FA-enabled account with no code → partial
    token + requires_2fa.
  * POST /auth/refresh — mints a fresh access token from the refresh
    cookie set by login; missing cookie → 401; wrong token type → 401.
  * POST /auth/logout — blacklists the presented access + refresh tokens.

Rate limiting: /auth/login carries ``@limiter.limit("5/minute")`` keyed on
the ``X-Real-IP`` header (falling back to a single shared bucket). To keep
the throttle from bleeding across tests in one session, each test sends a
unique X-Real-IP so it gets its own bucket, and never issues >5 logins.

Skipped (needs infra not practical to stand up in a unit DB harness):
  * LDAP / SAML login + JIT provisioning (directory server / IdP + certs).
  * Full TOTP verify-2fa round trip (needs a real encrypted secret + a
    live RFC-6238 code); the *pending-token* branch is covered without it.
  * forgot/reset-password email dispatch (SMTP); token-shape guards on
    reset-password are not exercised here.
"""

from __future__ import annotations

import uuid

import pytest

from sqlalchemy import select

from models.user import User


LOGIN_PW = "Sup3rSecret!pw"


def _ip_headers() -> dict:
    """A unique X-Real-IP so each test owns its own rate-limit bucket."""
    return {"X-Real-IP": f"10.0.0.{uuid.uuid4().int % 250 + 1}-{uuid.uuid4().hex[:8]}"}


# ── login: happy path ────────────────────────────────────────────────


async def test_login_correct_credentials_returns_access_token(client, make_user):
    user = await make_user(username="loginhappy", password=LOGIN_PW)

    resp = await client.post(
        "/auth/login",
        json={"username": "loginhappy", "password": LOGIN_PW},
        headers=_ip_headers(),
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert body["requires_2fa"] is False
    # Refresh token rides an HttpOnly cookie, not the JSON body (GHSA-gv65).
    assert body["refresh_token"] == ""
    assert client.cookies.get("refresh_token")
    assert user.username == "loginhappy"


async def test_login_is_case_insensitive_on_username(client, make_user):
    # UserLogin canonicalises (NFKC + casefold); a mixed-case submission
    # still resolves to the lowercased stored row.
    await make_user(username="casefolduser", password=LOGIN_PW)

    resp = await client.post(
        "/auth/login",
        json={"username": "CaseFoldUser", "password": LOGIN_PW},
        headers=_ip_headers(),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["access_token"]


# ── login: failure branches ──────────────────────────────────────────


async def test_login_wrong_password_401(client, make_user):
    await make_user(username="wrongpw", password=LOGIN_PW)

    resp = await client.post(
        "/auth/login",
        json={"username": "wrongpw", "password": "not-the-password"},
        headers=_ip_headers(),
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Incorrect username or password"


async def test_login_unknown_user_401(client):
    # Hits the dummy-hash constant-time branch (no such user).
    resp = await client.post(
        "/auth/login",
        json={"username": "nobody_here", "password": LOGIN_PW},
        headers=_ip_headers(),
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Incorrect username or password"


async def test_login_inactive_user_403(client, make_user):
    await make_user(username="inactiveuser", password=LOGIN_PW, is_active=False)

    resp = await client.post(
        "/auth/login",
        json={"username": "inactiveuser", "password": LOGIN_PW},
        headers=_ip_headers(),
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Inactive user account"


async def test_login_2fa_enabled_returns_partial_token(client, make_user):
    # totp_secret only needs to be truthy: with no totp_code supplied the
    # handler short-circuits to the partial-token branch BEFORE decrypting.
    await make_user(
        username="twofactor",
        password=LOGIN_PW,
        totp_enabled=True,
        totp_secret="not-a-real-secret",
    )

    resp = await client.post(
        "/auth/login",
        json={"username": "twofactor", "password": LOGIN_PW},
        headers=_ip_headers(),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["requires_2fa"] is True
    assert body["access_token"]  # short-lived 2fa-pending token
    assert body["refresh_token"] == ""
    # No refresh cookie should be issued for a not-yet-complete login.
    assert client.cookies.get("refresh_token") is None


async def test_login_validation_missing_password_422(client, make_user):
    await make_user(username="novalpw", password=LOGIN_PW)
    resp = await client.post(
        "/auth/login",
        json={"username": "novalpw"},
        headers=_ip_headers(),
    )
    assert resp.status_code == 422


# ── refresh flow ─────────────────────────────────────────────────────


async def test_refresh_after_login_mints_new_access_token(client, make_user):
    await make_user(username="refreshuser", password=LOGIN_PW)

    login = await client.post(
        "/auth/login",
        json={"username": "refreshuser", "password": LOGIN_PW},
        headers=_ip_headers(),
    )
    assert login.status_code == 200, login.text
    # httpx carries the refresh_token cookie forward automatically.
    assert client.cookies.get("refresh_token")

    resp = await client.post("/auth/refresh")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"


async def test_refresh_without_cookie_401(client):
    # Fresh client with no login → no refresh cookie present.
    assert client.cookies.get("refresh_token") is None
    resp = await client.post("/auth/refresh")
    assert resp.status_code == 401
    assert "Missing refresh-token cookie" in resp.json()["detail"]


async def test_refresh_rejects_access_token_as_cookie(client, make_user):
    # An access token (type="access") presented in the refresh cookie must
    # be rejected — only type="refresh" is accepted.
    await make_user(username="badtype", password=LOGIN_PW)
    login = await client.post(
        "/auth/login",
        json={"username": "badtype", "password": LOGIN_PW},
        headers=_ip_headers(),
    )
    access = login.json()["access_token"]

    resp = await client.post("/auth/refresh", cookies={"refresh_token": access})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid refresh token"


# ── logout / blacklist ───────────────────────────────────────────────


async def test_logout_blacklists_tokens(client, make_user):
    await make_user(username="logoutuser", password=LOGIN_PW)

    login = await client.post(
        "/auth/login",
        json={"username": "logoutuser", "password": LOGIN_PW},
        headers=_ip_headers(),
    )
    assert login.status_code == 200, login.text
    access = login.json()["access_token"]
    # Capture the refresh cookie now — logout clears it from the browser jar.
    refresh_cookie = client.cookies.get("refresh_token")
    assert refresh_cookie

    resp = await client.post(
        "/auth/logout",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["message"] == "Successfully logged out"

    # Re-present the (now-blacklisted) refresh token explicitly: logout
    # deletes the cookie AND blacklists the token, so a replay must 401.
    after = await client.post(
        "/auth/refresh", cookies={"refresh_token": refresh_cookie}
    )
    assert after.status_code == 401
    assert "revoked" in after.json()["detail"].lower()


# ── register (local) sanity ──────────────────────────────────────────


async def test_register_reserved_username_rejected(client):
    # No registration code needed — the reserved-name guard runs first and
    # returns a specific message before any code / uniqueness check.
    resp = await client.post(
        "/auth/register",
        json={
            "username": "admin",
            "email": "x@example.com",
            "password": "abcd1234!",
            "registration_code": "whatever",
        },
        headers=_ip_headers(),
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "That username is reserved."


async def test_register_without_code_generic_failure(client):
    resp = await client.post(
        "/auth/register",
        json={
            "username": "freshuser1",
            "email": "freshuser1@example.com",
            "password": "abcd1234!",
        },
        headers=_ip_headers(),
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Registration failed"
