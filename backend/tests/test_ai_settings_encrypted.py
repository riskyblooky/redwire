"""AI settings (the provider API key above all) are encrypted at rest."""

from __future__ import annotations

from sqlalchemy import text

KEY = "sk-test-0123456789abcdefSECRET"


async def test_api_key_is_ciphertext_in_the_database(client, db_session, make_user, authenticate_as):
    from routers.ai import _get_ai_settings
    admin = await make_user(role="admin")
    authenticate_as(admin)

    r = await client.put("/ai/settings", json={"ai_api_key": KEY})
    assert r.status_code == 200, r.text

    raw = (await db_session.execute(text("SELECT value FROM ai_settings WHERE key = 'ai_api_key'"))).scalar_one()
    assert KEY not in raw and raw.startswith("gAAAA")
    assert (await _get_ai_settings(db_session))["ai_api_key"] == KEY
    assert KEY not in (await client.get("/ai/settings")).text


async def test_boot_backfill_encrypts_a_legacy_plaintext_row(db_session):
    from utils.vault_crypto import decrypt_field
    from utils.vault_field_migration import backfill_legacy_vault_fields
    await db_session.execute(text("DELETE FROM ai_settings WHERE key = 'ai_api_key'"))
    await db_session.execute(text(
        "INSERT INTO ai_settings (key, value, is_encrypted) VALUES ('ai_api_key', :v, true)"), {"v": KEY})

    await backfill_legacy_vault_fields(db_session)

    raw = (await db_session.execute(text("SELECT value FROM ai_settings WHERE key = 'ai_api_key'"))).scalar_one()
    assert raw != KEY and decrypt_field(raw) == KEY


async def test_a_legacy_empty_value_reads_back_empty(db_session):
    from routers.ai import _get_ai_settings
    await db_session.execute(text("DELETE FROM ai_settings WHERE key = 'ai_extra_query'"))
    await db_session.execute(text("INSERT INTO ai_settings (key, value, is_encrypted) VALUES ('ai_extra_query', '', false)"))
    assert (await _get_ai_settings(db_session))["ai_extra_query"] == ""
