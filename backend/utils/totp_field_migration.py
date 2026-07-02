"""One-shot backfill for legacy unencrypted TOTP SECRETS.

GHSA-rp23-74j3-mqmq follow-up (TOTP half). The Alembic revision
``d7e8f9a0b1c2_widen_totp_secret`` on 2026-02-20 widened
``users.totp_secret`` to accommodate Fernet ciphertext but did not
touch existing rows. Users who enrolled 2FA before that revision
therefore still hold plaintext base32 seeds in the column. The
matching read helper ``auth.crypto.decrypt_totp_secret`` used to
fail-open on any value that did not decrypt cleanly, so legacy
plaintext round-tripped and the at-rest encryption guarantee
silently did not apply.

This backfill closes that gap on any upgraded deployment by walking
``users``, detecting rows whose ``totp_secret`` does not decrypt
under the current ``TOTP_ENCRYPTION_KEY``, and re-encrypting them in
place via raw SQL. The vault-side equivalent
(``backfill_legacy_vault_fields``) mirrors this shape for the four
vault tables — see that module for the deeper rationale on why raw
SQL rather than ORM is used.

A value that *looks* like a Fernet token (begins with ``gAAAAA``)
but fails to decrypt is treated as wrong-keyed / corrupted
ciphertext and **skipped**, not re-wrapped. Wrapping ciphertext-as-
plaintext would produce unrecoverable nested ciphertext; leaving
the row broken forces an operator to notice.
"""

from __future__ import annotations

import logging

from cryptography.fernet import InvalidToken
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from auth.crypto import _get_fernet

logger = logging.getLogger(__name__)

_FERNET_PREFIX = "gAAAAA"


def _is_decryptable(f, value: str) -> bool:
    try:
        f.decrypt(value.encode("utf-8"))
        return True
    except InvalidToken:
        return False


async def backfill_legacy_totp_secrets(db: AsyncSession) -> dict:
    """Idempotent walk of ``users.totp_secret`` re-encrypting any
    row whose value doesn't decrypt under the current TOTP key.
    Wrong-keyed Fernet values are preserved (skipped, not re-
    wrapped). Returns a stats dict for the caller to log.
    """
    stats = {
        "rows_checked": 0,
        "fields_already_encrypted": 0,
        "fields_re_encrypted": 0,
        "skipped": 0,
    }
    f = _get_fernet()

    result = await db.execute(sa_text(
        "SELECT id, totp_secret FROM users WHERE totp_secret IS NOT NULL"
    ))
    for row in result.fetchall():
        user_id, value = row[0], row[1]
        stats["rows_checked"] += 1

        if not isinstance(value, str) or value == "":
            continue
        if _is_decryptable(f, value):
            stats["fields_already_encrypted"] += 1
            continue
        if value.startswith(_FERNET_PREFIX):
            logger.warning(
                "totp-secret backfill: SKIPPING user %s — totp_secret "
                "looks like Fernet but failed to decrypt. Not re-wrapping "
                "(would lose recoverability). Investigate wrong-key / "
                "restored-backup / corruption.",
                user_id,
            )
            stats["skipped"] += 1
            continue

        try:
            new_ciphertext = f.encrypt(value.encode("utf-8")).decode("utf-8")
        except Exception as exc:
            logger.warning(
                "totp-secret backfill: skipping user %s — re-encrypt "
                "failed: %s", user_id, exc,
            )
            stats["skipped"] += 1
            continue

        await db.execute(
            sa_text("UPDATE users SET totp_secret = :v WHERE id = :i"),
            {"v": new_ciphertext, "i": user_id},
        )
        stats["fields_re_encrypted"] += 1

    if stats["fields_re_encrypted"]:
        await db.commit()
    if stats["fields_re_encrypted"] or stats["skipped"]:
        logger.info(
            "totp-secret backfill: rows_checked=%d already_encrypted=%d "
            "re_encrypted=%d skipped=%d",
            stats["rows_checked"], stats["fields_already_encrypted"],
            stats["fields_re_encrypted"], stats["skipped"],
        )
    return stats


async def count_legacy_totp_rows(db: AsyncSession) -> int:
    """Cheap probe: count users whose totp_secret is present but does
    not decrypt under the current key. Used by the boot hook to
    decide whether to print the backfill banner."""
    f = _get_fernet()
    bad = 0
    result = await db.execute(sa_text(
        "SELECT id, totp_secret FROM users WHERE totp_secret IS NOT NULL"
    ))
    for row in result.fetchall():
        value = row[1]
        if not isinstance(value, str) or value == "":
            continue
        if not _is_decryptable(f, value):
            bad += 1
    return bad
