"""Review sweep: auth and admin findings."""

from __future__ import annotations

import uuid

import pyotp
import pytest
from sqlalchemy import func, select

from auth import jwt as authjwt


async def _code_count(db, user_id):
    from models.recovery_code import RecoveryCode
    return (await db.execute(select(func.count()).select_from(RecoveryCode)
                             .where(RecoveryCode.user_id == user_id))).scalar_one()


async def test_password_reset_drops_recovery_codes(client, db_session, make_user):
    """Reset clears TOTP; the old codes would come back to life on re-enable."""
    from models.recovery_code import RecoveryCode
    user = await make_user()
    db_session.add(RecoveryCode(user_id=user.id, code_hash="x"))
    await db_session.flush()
    tok = authjwt.create_access_token({"sub": user.id, "type": "password_reset"})

    r = await client.post("/auth/reset-password", json={"token": tok, "new_password": "An0ther!Passw0rd"})

    assert r.status_code == 200, r.text
    assert await _code_count(db_session, user.id) == 0


async def test_enabling_2fa_replaces_earlier_codes(client, db_session, make_user, monkeypatch):
    import auth.dependencies as deps
    from models.recovery_code import RecoveryCode
    monkeypatch.setattr(deps, "is_token_blacklisted", lambda _t: False)
    user = await make_user()
    db_session.add(RecoveryCode(user_id=user.id, code_hash="stale"))
    await db_session.flush()
    h = {"Authorization": f"Bearer {authjwt.create_access_token({'sub': user.id})}"}

    setup = await client.post("/auth/totp/setup", headers=h, json={"password": "Sup3rSecret!pw"})
    r = await client.post("/auth/totp/verify-setup", headers=h,
                          json={"code": pyotp.TOTP(setup.json()["secret"]).now()})

    assert r.status_code == 200, r.text
    hashes = (await db_session.execute(select(RecoveryCode.code_hash)
                                       .where(RecoveryCode.user_id == user.id))).scalars().all()
    assert "stale" not in hashes and len(hashes) == len(r.json()["recovery_codes"])


async def test_ldap_bind_password_is_fully_masked(client, db_session, make_user, authenticate_as):
    from models.auth_settings import AuthSetting
    db_session.add(AuthSetting(key="ldap_bind_password", value="Sup3rSecretBindPw"))
    await db_session.flush()
    admin = await make_user(role="admin")
    authenticate_as(admin)

    r = await client.get("/admin/auth-settings")

    assert r.status_code == 200, r.text
    masked = r.json()["ldap"]["bind_password"]
    assert masked and "Sup3" not in masked and "dPw" not in masked


@pytest.mark.parametrize("change", [{"role": "operator"}, {"is_active": False}])
async def test_last_active_admin_cannot_be_demoted_or_deactivated(change, client, db_session, make_user,
                                                                   authenticate_as):
    from sqlalchemy import update
    from models.user import User, UserRole
    admin = await make_user(role="admin")
    # Only this one admin in the (rolled-back) test transaction.
    await db_session.execute(update(User).where(User.role == UserRole.ADMIN, User.id != admin.id)
                             .values(is_active=False))
    authenticate_as(admin)
    db_session.expunge_all()  # the handler loads its own copy, as in a real request

    r = await client.patch(f"/admin/users/{admin.id}", json=change)
    assert r.status_code == 400, r.text

    second = await make_user(role="admin")
    db_session.expunge_all()
    r = await client.patch(f"/admin/users/{second.id}", json=change)
    assert r.status_code == 200, r.text


async def test_admin_email_change_to_a_taken_address_is_409(client, db_session, make_user, authenticate_as):
    admin = await make_user(role="admin")
    a = await make_user(email=f"a-{uuid.uuid4().hex[:8]}@example.com")
    b = await make_user(email=f"b-{uuid.uuid4().hex[:8]}@example.com")
    authenticate_as(admin)
    db_session.expunge_all()

    r = await client.patch(f"/admin/users/{a.id}", json={"email": b.email})
    assert r.status_code == 409, r.text


async def test_admin_email_change_is_audited(client, db_session, make_user, authenticate_as, monkeypatch):
    import routers.admin as admin_router
    events = []

    async def _record(kind, **kw):
        events.append((kind, kw.get("details")))
    monkeypatch.setattr(admin_router, "record_security_event", _record)
    admin = await make_user(role="admin")
    a = await make_user(email=f"a-{uuid.uuid4().hex[:8]}@example.com")
    authenticate_as(admin)
    db_session.expunge_all()

    r = await client.patch(f"/admin/users/{a.id}", json={"email": f"new-{uuid.uuid4().hex[:8]}@example.com"})
    assert r.status_code == 200, r.text
    assert events and "email" in events[-1][1]["changes"]


def test_totp_code_against_a_missing_secret_is_just_invalid():
    """decrypt_totp_secret returns None for an undecryptable secret; every
    caller passed that on and got a TypeError (a 500 at login)."""
    from auth.totp import verify_totp_code
    assert verify_totp_code(None, "123456") is None
    assert verify_totp_code("", "123456") is None


def test_api_token_expiry_offset_is_converted_not_dropped():
    from datetime import datetime, timedelta, timezone
    from routers.api_tokens import _naive_utc
    plus5 = datetime(2026, 6, 1, 12, 0, tzinfo=timezone(timedelta(hours=5)))
    assert _naive_utc(plus5) == datetime(2026, 6, 1, 7, 0)
    assert _naive_utc(datetime(2026, 6, 1, 12, 0)) == datetime(2026, 6, 1, 12, 0)
    assert _naive_utc(None) is None

