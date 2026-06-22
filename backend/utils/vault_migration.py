"""One-shot backfill for legacy unencrypted vault FILE blobs.

GHSA-3r7j-7h5r-gxgx Issue 3 follow-up. RDW-057 wired Fernet encryption
into the vault file-upload path; any blob uploaded *before* that fix
sits in MinIO as plaintext. The download path's ``decrypt_bytes``
fallback handles them transparently — but they're still readable to
anyone with direct bucket access (misconfigured policy, leaked
storage credentials, server-side file-read primitive).

This module's job: walk every ``vault_items`` row flagged
``encryption_version = 0`` (set by the schema migration on existing
file-bearing rows), download the blob, encrypt it if it isn't
already Fernet ciphertext, re-upload to the same storage key, bump
the flag to 1. Idempotent — safe to re-run; once all rows are at
version 1 the helper returns immediately.

Skip + log on any per-row error (unreadable from MinIO, missing
object, bucket access denied, …). An unreachable blob is already
broken from the user's perspective — the helper shouldn't abort the
whole boot loop trying to fix it.
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from models.vault import VaultItem
from utils.storage import storage_service
from utils.vault_crypto import encrypt_bytes

logger = logging.getLogger(__name__)


# Fernet ciphertext begins with the version byte 0x80 ("\x80"), then
# the timestamp + IV + payload + HMAC, base64-url-encoded. The
# url-safe base64 of the leading 0x80 byte is "g". A Fernet token
# therefore starts with "gAAAAA" in its base64 form — cheap shape
# check used to skip already-encrypted blobs during the backfill.
_FERNET_PREFIX = b"gAAAAA"


def _is_already_fernet(blob: bytes) -> bool:
    """True if the blob looks like a Fernet token (encrypted under our
    scheme). Used by the backfill to skip the encrypt-and-re-upload
    round-trip on rows that are already at-rest encrypted.

    Cheap prefix check rather than a real decrypt attempt — the goal
    is "definitely Fernet vs probably not." False negatives just cost
    an extra re-encrypt round; false positives would skip a legitimate
    plaintext file that happens to start with ``gAAAAA``, which is
    astronomically unlikely.
    """
    return isinstance(blob, bytes) and blob[: len(_FERNET_PREFIX)] == _FERNET_PREFIX


async def count_legacy_blobs(db: AsyncSession) -> int:
    """How many vault FILE rows still need backfill. Used by the
    startup hook to decide whether to run."""
    result = await db.execute(
        select(func.count())
        .select_from(VaultItem)
        .where(VaultItem.encryption_version == 0)
        .where(VaultItem.file_path.is_not(None))
    )
    return result.scalar() or 0


async def backfill_legacy_vault_blobs(db: AsyncSession) -> dict[str, int]:
    """Walk every ``vault_items`` row at ``encryption_version=0`` with a
    non-NULL ``file_path``. For each:

      1. Download the MinIO blob.
      2. If already Fernet-shaped: just bump ``encryption_version`` to 1.
      3. Otherwise: encrypt, re-upload to the same storage key, then
         bump the flag.

    On any per-row error (download failure, upload failure, etc.) log
    + skip — the row stays at version 0 and the next boot retries it.

    Returns a stats dict: ``{checked, already_encrypted, encrypted_now,
    skipped}``. Callers log it.
    """
    stats = {"checked": 0, "already_encrypted": 0, "encrypted_now": 0, "skipped": 0}

    result = await db.execute(
        select(VaultItem)
        .where(VaultItem.encryption_version == 0)
        .where(VaultItem.file_path.is_not(None))
    )
    legacy_rows = result.scalars().all()

    for row in legacy_rows:
        stats["checked"] += 1
        try:
            blob = await storage_service.download_file(row.file_path)
        except Exception as e:
            logger.warning(
                "vault-encryption backfill: skipping row %s (file_path=%r): "
                "download failed: %s",
                row.id, row.file_path, e,
            )
            stats["skipped"] += 1
            continue

        if blob is None:
            logger.warning(
                "vault-encryption backfill: skipping row %s (file_path=%r): "
                "MinIO returned None",
                row.id, row.file_path,
            )
            stats["skipped"] += 1
            continue

        if _is_already_fernet(blob):
            row.encryption_version = 1
            stats["already_encrypted"] += 1
            continue

        try:
            ciphertext = encrypt_bytes(blob)
            await storage_service.upload_file(
                ciphertext,
                row.file_path,
                content_type="application/octet-stream",
            )
            row.encryption_version = 1
            stats["encrypted_now"] += 1
        except Exception as e:
            logger.warning(
                "vault-encryption backfill: skipping row %s (file_path=%r): "
                "encrypt-and-re-upload failed: %s",
                row.id, row.file_path, e,
            )
            stats["skipped"] += 1
            continue

    if stats["checked"]:
        await db.commit()
        logger.info(
            "vault-encryption backfill complete: checked=%d, already_encrypted=%d, "
            "encrypted_now=%d, skipped=%d",
            stats["checked"], stats["already_encrypted"],
            stats["encrypted_now"], stats["skipped"],
        )
    return stats
