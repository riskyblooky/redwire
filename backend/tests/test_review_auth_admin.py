"""Review sweep: auth and admin findings."""

from __future__ import annotations

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
