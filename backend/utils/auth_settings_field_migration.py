"""One-shot backfill for legacy plaintext ``auth_settings.value`` rows.

Companion to switching ``AuthSetting.value`` from ``Text`` to
``EncryptedText``. Before that change, LDAP bind passwords, SMTP
passwords, SAML IdP certs, and TLS CA certs sat in the DB as plaintext
even though the model flagged them ``is_encrypted=True`` (the flag was
only used for API-response masking, not for actual encryption). Every
row's ``value`` is now Fernet-wrapped at the column-type layer; this
backfill walks the table once at boot, detects rows still holding
plaintext, and re-encrypts in place so the fail-closed decrypt on
subsequent reads doesn't nuke the operator's LDAP/SMTP config.

Every value is now encrypted regardless of ``is_encrypted``. Non-secret
rows like ``ldap_server_url`` get encrypted too — it's a small waste
of CPU, but it means the type layer is uniform and there is no
"plaintext substrate" code path through the ORM at all.

Implementation matches ``vault_field_migration.py``:
  - Raw SQL bypasses the ``EncryptedText`` column type so the migration
    of the crypto layer itself is safe.
  - Values that already decrypt under the current key are left alone.
  - Values that *look* like Fernet (start with ``gAAAAA``) but fail to
    decrypt are wrong-keyed / corrupted ciphertext — skipped, not
    re-wrapped (wrapping ciphertext-as-plaintext would produce
    unrecoverable double-encryption).
"""

from __future__ import annotations

import logging

from cryptography.fernet import InvalidToken
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from utils.vault_crypto import _get_fernet

logger = logging.getLogger(__name__)


_FERNET_PREFIX = "gAAAAA"


def _is_decryptable(f, value: str) -> bool:
    try:
        f.decrypt(value.encode("utf-8"))
        return True
    except InvalidToken:
        return False


async def backfill_legacy_auth_settings(db: AsyncSession) -> dict:
    """Idempotent walk of ``auth_settings``. Plaintext rows get
    re-encrypted; already-Fernet rows are left alone. Returns a stats
    dict for the caller to log.
    """
    stats = {
        "rows_checked": 0,
        "already_encrypted": 0,
        "re_encrypted": 0,
        "skipped": 0,
    }
    f = _get_fernet()

    result = await db.execute(sa_text("SELECT key, value FROM auth_settings"))
    for row in result.fetchall():
        key, value = row[0], row[1]
        stats["rows_checked"] += 1

        if value is None or value == "" or not isinstance(value, str):
            continue

        if _is_decryptable(f, value):
            stats["already_encrypted"] += 1
            continue

        if value.startswith(_FERNET_PREFIX):
            logger.warning(
                "auth-settings backfill: SKIPPING key=%r — value looks like "
                "Fernet but failed to decrypt. Not re-wrapping (would lose "
                "recoverability). Investigate wrong-key / restored-backup / "
                "corruption.", key,
            )
            stats["skipped"] += 1
            continue

        try:
            new_value = f.encrypt(value.encode("utf-8")).decode("utf-8")
        except Exception as exc:
            logger.warning(
                "auth-settings backfill: skipping key=%r — re-encrypt failed: %s",
                key, exc,
            )
            stats["skipped"] += 1
            continue

        await db.execute(
            sa_text("UPDATE auth_settings SET value = :val WHERE key = :key"),
            {"val": new_value, "key": key},
        )
        stats["re_encrypted"] += 1

    if stats["re_encrypted"]:
        await db.commit()
        logger.info(
            "auth-settings backfill: rows_checked=%d already_encrypted=%d "
            "re_encrypted=%d skipped=%d",
            stats["rows_checked"], stats["already_encrypted"],
            stats["re_encrypted"], stats["skipped"],
        )
    return stats


async def count_legacy_auth_settings_rows(db: AsyncSession) -> int:
    """Count auth_settings rows carrying a value that doesn't decrypt
    under the current key. Cheap probe used by the boot hook to decide
    whether to print the backfill banner."""
    f = _get_fernet()
    bad = 0
    result = await db.execute(sa_text("SELECT value FROM auth_settings"))
    for row in result.fetchall():
        v = row[0]
        if v is None or v == "" or not isinstance(v, str):
            continue
        if not _is_decryptable(f, v):
            bad += 1
    return bad
