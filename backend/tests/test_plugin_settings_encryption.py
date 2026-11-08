"""plugin_settings.value is encrypted at rest (EncryptedText), legacy
plaintext rows are re-encrypted by the boot backfill, and the Security
Center posture check reports plaintext secrets."""

from __future__ import annotations

import uuid

from sqlalchemy import select, text

from models.plugin import PluginSetting


async def _raw(db, row_id):
    return (await db.execute(text("SELECT value FROM plugin_settings WHERE id = :i"), {"i": row_id})).scalar_one()


async def _insert_raw(db, value, is_secret=True, key="API_KEY"):
    row_id = str(uuid.uuid4())
    await db.execute(
        text("INSERT INTO plugin_settings (id, plugin_id, key, value, is_secret) VALUES (:i, 'p_test', :k, :v, :s)"),
        {"i": row_id, "k": key, "v": value, "s": is_secret},
    )
    return row_id


async def test_orm_writes_ciphertext_and_reads_plaintext(db_session):
    row = PluginSetting(plugin_id="p_test", key="API_KEY", value="sk-live-123456", is_secret=True)
    db_session.add(row)
    await db_session.flush()
    row_id = row.id
    raw = await _raw(db_session, row_id)
    assert raw != "sk-live-123456" and raw.startswith("gAAAAA")
    db_session.expire(row)
    got = (await db_session.execute(select(PluginSetting).where(PluginSetting.id == row_id))).scalar_one()
    assert got.value == "sk-live-123456"


async def test_backfill_encrypts_plaintext_and_is_idempotent(db_session):
    from utils.plugin_settings_field_migration import (
        backfill_legacy_plugin_settings, count_legacy_plugin_settings_rows,
    )
    plain = await _insert_raw(db_session, "hunter2")
    empty = await _insert_raw(db_session, "", key="EMPTY")
    bogus = await _insert_raw(db_session, "gAAAAAnot-really-fernet", key="BOGUS")
    nul = await _insert_raw(db_session, None, key="NULL")
    assert await count_legacy_plugin_settings_rows(db_session) == 3  # plain, empty, bogus

    stats = await backfill_legacy_plugin_settings(db_session)
    assert stats["re_encrypted"] == 2 and stats["skipped"] == 1

    assert (await _raw(db_session, plain)).startswith("gAAAAA")
    assert await _raw(db_session, bogus) == "gAAAAAnot-really-fernet"  # never double-wrapped
    assert await _raw(db_session, nul) is None
    rows = {r.key: r.value for r in (await db_session.execute(
        select(PluginSetting).where(PluginSetting.plugin_id == "p_test").execution_options(populate_existing=True)
    )).scalars()}
    assert rows["API_KEY"] == "hunter2" and rows["EMPTY"] == ""

    again = await backfill_legacy_plugin_settings(db_session)
    assert again["re_encrypted"] == 0
    assert await count_legacy_plugin_settings_rows(db_session) == 1  # only the bogus row remains


async def test_posture_flags_plaintext_plugin_secret(client, db_session, make_user, authenticate_as, monkeypatch):
    from routers import security_center
    monkeypatch.setattr(security_center, "_tls_cert_days", lambda *_a, **_k: (_ for _ in ()).throw(OSError()))
    authenticate_as(await make_user(role="admin"))

    async def check():
        data = (await client.get("/admin/security/posture", params={"refresh": True})).json()
        return next(c for c in data["checks"] if c["id"] == "plugin_secrets")

    await _insert_raw(db_session, "plain-config", is_secret=False, key="URL")  # non-secret: not reported
    assert (await check())["status"] == "pass"
    await _insert_raw(db_session, "plain-secret")
    assert (await check())["status"] == "fail"
