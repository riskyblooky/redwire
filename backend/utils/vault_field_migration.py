"""One-shot backfill for legacy unencrypted vault SECRET COLUMNS.

GHSA-3r7j-7h5r-gxgx follow-up. ``encrypt_field`` writes a Fernet token
into the username / password / note columns on the vault tables, but
the matching ``decrypt_field`` silently returned the raw value on any
decrypt failure — so a write path that ever forgot to encrypt (3r7j
itself was one such bug on the import side) wrote plaintext into the
column and the read-back path silently confirmed it. The vault UI
looked normal; the bug was invisible.

This module's job: walk every row in the four tables that store
Fernet-encrypted secret columns, try to decrypt each non-empty value
under the current ``VAULT_ENCRYPTION_KEY``, and on failure encrypt as
legacy plaintext. Idempotent — safe to re-run on every boot, fast
when there's nothing to do (Fernet decrypt is microseconds per value).

Once this has run cleanly across the deployment, ``decrypt_field`` can
be flipped to fail-closed (return ``None`` + log) so any future
write-path bug surfaces in the UI instead of being round-tripped.

Tables covered (matching every callsite of ``encrypt_field`` /
``decrypt_field``):

  - ``vault_items`` — username / password / note
  - ``infra_vault_items`` — username / password / note
  - ``spray_campaigns`` — password_used
  - ``spray_results`` — username / password

A value that *looks* like a Fernet token (begins with ``gAAAAA``,
the base64-url framing of the version byte) but fails to decrypt is
treated as wrong-keyed / corrupted ciphertext and **skipped**, not
re-wrapped. Wrapping ciphertext-as-plaintext would produce
unrecoverable nested ciphertext — better to leave the row visibly
broken so the operator notices and can investigate (key rotation
mishap, restored backup with stale key, etc.).
"""

from __future__ import annotations

import logging
from typing import Tuple

from cryptography.fernet import InvalidToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from utils.vault_crypto import _get_fernet

logger = logging.getLogger(__name__)


# A Fernet token, base64-url-encoded, always begins with "gAAAAA" — that
# is the base64 framing of the version byte 0x80 plus zero-padding for
# the leading bytes of the timestamp. A value with this prefix that
# nevertheless fails to decrypt is almost certainly wrong-keyed Fernet
# (or corrupted) — NOT plaintext that happens to start with `g`. Skip
# those rather than wrapping them.
_FERNET_PREFIX = "gAAAAA"


_FieldsForRow = Tuple[str, ...]


def _backfill_row_fields(row, columns: _FieldsForRow, f, stats: dict) -> bool:
    """Walk the named columns on ``row``. Returns True if any column on
    the row was mutated (caller commits)."""
    changed = False
    for col in columns:
        v = getattr(row, col, None)
        if v is None or v == "":
            continue
        if not isinstance(v, str):
            # Defensive — every encrypted column is Text, so this should
            # never fire. Log + skip rather than mutate.
            logger.warning(
                "vault-field backfill: skipping %s.%s on row %s — "
                "non-str value of type %s",
                type(row).__name__, col, getattr(row, "id", "?"), type(v).__name__,
            )
            stats["skipped"] += 1
            continue
        try:
            f.decrypt(v.encode("utf-8"))
            stats["fields_already_encrypted"] += 1
        except InvalidToken:
            if v.startswith(_FERNET_PREFIX):
                # Looks like Fernet but didn't decrypt under our key —
                # likely wrong-keyed ciphertext (rotation mistake, restored
                # backup with a stale key, corruption). Leave it alone so
                # operator can investigate / recover with the right key.
                logger.warning(
                    "vault-field backfill: SKIPPING %s.%s on row %s — "
                    "value looks like Fernet but failed to decrypt. "
                    "Not re-wrapping (would lose recoverability). "
                    "Investigate wrong-key / restored-backup / corruption.",
                    type(row).__name__, col, getattr(row, "id", "?"),
                )
                stats["skipped"] += 1
                continue
            # Legacy plaintext — encrypt in place.
            try:
                new = f.encrypt(v.encode("utf-8")).decode("utf-8")
                setattr(row, col, new)
                changed = True
                stats["fields_re_encrypted"] += 1
            except Exception as exc:
                logger.warning(
                    "vault-field backfill: skipping %s.%s on row %s — "
                    "re-encrypt failed: %s",
                    type(row).__name__, col, getattr(row, "id", "?"), exc,
                )
                stats["skipped"] += 1
    return changed


# Each entry: (model class, columns to walk). Kept in one place so the
# boot hook + tests + future maintainers see the full scope at a glance.
def _table_specs():
    from models.vault import VaultItem
    from models.infra_vault_item import InfraVaultItem
    from models.spray import SprayCampaign, SprayResult
    return [
        (VaultItem, ("username", "password", "note")),
        (InfraVaultItem, ("username", "password", "note")),
        (SprayCampaign, ("password_used",)),
        (SprayResult, ("username", "password")),
    ]


async def backfill_legacy_vault_fields(db: AsyncSession) -> dict:
    """Idempotent walk of every Fernet-encrypted secret column across
    the four vault tables. On failure-to-decrypt: re-encrypt as legacy
    plaintext, or skip if the value looks like a wrong-keyed Fernet
    token. Returns a stats dict for the caller to log."""
    stats = {
        "rows_checked": 0,
        "fields_already_encrypted": 0,
        "fields_re_encrypted": 0,
        "skipped": 0,
    }
    f = _get_fernet()
    any_changed = False

    for model, columns in _table_specs():
        result = await db.execute(select(model))
        for row in result.scalars().all():
            stats["rows_checked"] += 1
            if _backfill_row_fields(row, columns, f, stats):
                any_changed = True

    if any_changed:
        await db.commit()
    if stats["fields_re_encrypted"] or stats["skipped"]:
        logger.info(
            "vault-field backfill: rows_checked=%d already_encrypted=%d "
            "re_encrypted=%d skipped=%d",
            stats["rows_checked"], stats["fields_already_encrypted"],
            stats["fields_re_encrypted"], stats["skipped"],
        )
    return stats


async def count_legacy_field_rows(db: AsyncSession) -> int:
    """Count of distinct rows that carry at least one secret column
    which doesn't decrypt under the current key. Used by the boot
    hook to print a meaningful "backfilling N rows..." line vs
    silently no-op'ing when there's nothing to do.

    Walks the same row set the backfill would — but stops at the first
    bad column per row so the cost is bounded."""
    f = _get_fernet()
    bad = 0
    for model, columns in _table_specs():
        result = await db.execute(select(model))
        for row in result.scalars().all():
            for col in columns:
                v = getattr(row, col, None)
                if v is None or v == "" or not isinstance(v, str):
                    continue
                try:
                    f.decrypt(v.encode("utf-8"))
                except InvalidToken:
                    bad += 1
                    break  # one bad column already disqualifies the row
    return bad
