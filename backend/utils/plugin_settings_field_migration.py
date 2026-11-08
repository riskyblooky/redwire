"""One-shot backfill for legacy plaintext ``plugin_settings.value`` rows.

Companion to switching ``PluginSetting.value`` from ``Text`` to
``EncryptedText``. Plugin ``type: secret`` settings (the ServiceNow
password, the Shodan API key) were masked in the API but stored in
plaintext. Every row is now Fernet-wrapped at the column-type layer; this
walks the table once at boot and re-encrypts rows still holding plaintext,
so the fail-closed decrypt doesn't blank out a plugin's configuration on
first upgrade.

Same rules as ``auth_settings_field_migration``: raw SQL (bypasses the
column type), values that already decrypt are left alone, and values that
look like Fernet but don't decrypt are skipped rather than double-wrapped.
"""

from __future__ import annotations

import logging

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from utils.auth_settings_field_migration import _FERNET_PREFIX, _is_decryptable
from utils.vault_crypto import _get_fernet

logger = logging.getLogger(__name__)


async def backfill_legacy_plugin_settings(db: AsyncSession) -> dict:
    stats = {"rows_checked": 0, "already_encrypted": 0, "re_encrypted": 0, "skipped": 0}
    f = _get_fernet()

    result = await db.execute(sa_text("SELECT id, plugin_id, key, value FROM plugin_settings"))
    for row_id, plugin_id, key, value in result.fetchall():
        stats["rows_checked"] += 1
        if value is None or not isinstance(value, str):
            continue
        if value and _is_decryptable(f, value):
            stats["already_encrypted"] += 1
            continue
        if value.startswith(_FERNET_PREFIX):
            logger.warning(
                "plugin-settings backfill: SKIPPING %s/%s — value looks like Fernet but "
                "failed to decrypt (wrong key / restored backup / corruption).", plugin_id, key,
            )
            stats["skipped"] += 1
            continue
        await db.execute(
            sa_text("UPDATE plugin_settings SET value = :val WHERE id = :id"),
            {"val": f.encrypt(value.encode("utf-8")).decode("utf-8"), "id": row_id},
        )
        stats["re_encrypted"] += 1

    if stats["re_encrypted"]:
        await db.commit()
    return stats


async def count_legacy_plugin_settings_rows(db: AsyncSession, secrets_only: bool = False) -> int:
    """Rows whose value doesn't decrypt under the current key (plaintext or
    bad ciphertext). ``secrets_only`` limits it to ``type: secret`` settings."""
    f = _get_fernet()
    q = "SELECT value FROM plugin_settings" + (" WHERE is_secret" if secrets_only else "")
    bad = 0
    for (v,) in (await db.execute(sa_text(q))).fetchall():
        if v is None or not isinstance(v, str):
            continue
        if v == "" or not _is_decryptable(f, v):
            bad += 1
    return bad
