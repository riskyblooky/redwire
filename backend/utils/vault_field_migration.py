"""One-shot backfill for legacy unencrypted vault SECRET COLUMNS.

GHSA-3r7j-7h5r-gxgx follow-up. The vault secret columns
(username/password/note across four tables) are now Fernet-encrypted
at the SQLAlchemy column-type layer via ``EncryptedText`` —
encrypt-on-bind, decrypt-on-read. Routers see plaintext on both
sides. Once that wiring is in place, any legacy row that still holds
plaintext at rest will fail-closed to ``None`` on read (per
``decrypt_field``'s stricter contract). This backfill is what makes
that flip safe on an upgrade — it walks every secret column once,
detects rows storing plaintext, and re-encrypts in place.

Implementation note: the helper uses **raw SQL** (``sa.text(...)``)
intentionally. Going through the ORM would route reads/writes
through ``EncryptedText``, which would (a) decrypt every read so a
plaintext value would appear "broken" rather than detectable, and
(b) re-encrypt every write so an in-place fix would land double-
wrapped. Raw SQL bypasses the column type and operates on the
literal cell bytes — the only safe substrate for a migration of the
crypto layer itself.

Tables covered (matching every Fernet-encrypted secret column in the
schema):

  - ``vault_items`` — username / password / note
  - ``infra_vault_items`` — username / password / note
  - ``spray_campaigns`` — password_used
  - ``spray_results`` — username / password

A value that *looks* like a Fernet token (begins with ``gAAAAA``,
the base64-url framing of the version byte) but fails to decrypt
is treated as wrong-keyed / corrupted ciphertext and **skipped**,
not re-wrapped. Wrapping ciphertext-as-plaintext would produce
unrecoverable nested ciphertext — better to leave the row visibly
broken so the operator notices.
"""

from __future__ import annotations

import logging
from typing import List, Tuple

from cryptography.fernet import InvalidToken
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from utils.vault_crypto import _get_fernet

logger = logging.getLogger(__name__)


# Fernet token framing — see _is_already_fernet in vault_migration.py
# for the blob analogue. A column value starting with this prefix
# that does NOT decrypt is almost certainly wrong-keyed Fernet, not
# plaintext that happens to start with "g".
_FERNET_PREFIX = "gAAAAA"


# (table_name, secret_columns). Kept in one place so a future encrypted
# column added elsewhere has a single registry entry to update — tests
# pin this list so a missed entry shows up as a noisy failure.
_TABLE_SPECS: List[Tuple[str, Tuple[str, ...]]] = [
    ("vault_items", ("username", "password", "note")),
    ("infra_vault_items", ("username", "password", "note")),
    ("spray_campaigns", ("password_used",)),
    ("spray_results", ("username", "password")),
]


def _is_decryptable(f, value: str) -> bool:
    try:
        f.decrypt(value.encode("utf-8"))
        return True
    except InvalidToken:
        return False


async def _walk_table(
    db: AsyncSession, table: str, columns: Tuple[str, ...], f, stats: dict
) -> None:
    """Raw-SQL pass: SELECT each row's id + secret columns, evaluate
    decrypt-status, UPDATE the row in place for any legacy-plaintext
    columns. Skips empty / None / wrong-keyed-Fernet values."""
    cols_sql = ", ".join(["id"] + list(columns))
    select_sql = f"SELECT {cols_sql} FROM {table}"  # noqa: S608 — table+cols from a constant registry, not user input
    result = await db.execute(sa_text(select_sql))

    for row in result.fetchall():
        row_id = row[0]
        # Map column name → value, indexed in the same order as cols_sql.
        col_values = dict(zip(columns, row[1:]))

        updates: dict[str, str] = {}
        for col in columns:
            v = col_values[col]
            if v is None or v == "" or not isinstance(v, str):
                continue
            if _is_decryptable(f, v):
                stats["fields_already_encrypted"] += 1
                continue
            if v.startswith(_FERNET_PREFIX):
                logger.warning(
                    "vault-field backfill: SKIPPING %s.%s on row %s — "
                    "value looks like Fernet but failed to decrypt. "
                    "Not re-wrapping (would lose recoverability). "
                    "Investigate wrong-key / restored-backup / corruption.",
                    table, col, row_id,
                )
                stats["skipped"] += 1
                continue
            # Legacy plaintext — schedule re-encrypt in this row's UPDATE.
            try:
                updates[col] = f.encrypt(v.encode("utf-8")).decode("utf-8")
            except Exception as exc:
                logger.warning(
                    "vault-field backfill: skipping %s.%s on row %s — "
                    "re-encrypt failed: %s", table, col, row_id, exc,
                )
                stats["skipped"] += 1

        if updates:
            # One UPDATE per row touched. SET clause is built from the
            # registry-derived `updates` keys (never user input).
            set_sql = ", ".join(f"{col} = :{col}" for col in updates)
            params = {**updates, "row_id": row_id}
            await db.execute(
                sa_text(f"UPDATE {table} SET {set_sql} WHERE id = :row_id"),
                params,
            )
            stats["fields_re_encrypted"] += len(updates)

        stats["rows_checked"] += 1


async def backfill_legacy_vault_fields(db: AsyncSession) -> dict:
    """Idempotent walk of every Fernet-encrypted secret column across
    the four vault tables. Plaintext rows get re-encrypted in place
    via raw SQL (so the EncryptedText column type doesn't interfere).
    Wrong-keyed Fernet values are preserved. Returns a stats dict for
    the caller to log.
    """
    stats = {
        "rows_checked": 0,
        "fields_already_encrypted": 0,
        "fields_re_encrypted": 0,
        "skipped": 0,
    }
    f = _get_fernet()

    for table, columns in _TABLE_SPECS:
        await _walk_table(db, table, columns, f, stats)

    if stats["fields_re_encrypted"]:
        await db.commit()
    if stats["fields_re_encrypted"] or stats["skipped"]:
        logger.info(
            "vault-field backfill: rows_checked=%d already_encrypted=%d "
            "re_encrypted=%d skipped=%d",
            stats["rows_checked"], stats["fields_already_encrypted"],
            stats["fields_re_encrypted"], stats["skipped"],
        )
    return stats


async def unwrap_double_encrypted_fields(db: AsyncSession) -> dict:
    """One-shot recovery for vault rows that were accidentally double-
    Fernet-encrypted. Idempotent: a single-encrypted value decrypts
    once to plaintext (not another Fernet token) and is left alone.

    Triggered by an earlier transient state in this codebase where the
    column-type EncryptedText was introduced while routers still
    called ``encrypt_field()`` explicitly, producing rows wrapped
    twice. Once fixed, the helper no-ops on subsequent boots
    (decrypt-once → plaintext for healthy single-encrypted rows).

    Operates via raw SQL to bypass the EncryptedText column type —
    going through the ORM would itself decrypt once on read and
    encrypt once on write, masking the corruption and re-introducing
    it on commit.
    """
    stats = {"rows_checked": 0, "unwrapped": 0, "left_alone": 0}
    f = _get_fernet()

    for table, columns in _TABLE_SPECS:
        cols_sql = ", ".join(["id"] + list(columns))
        result = await db.execute(sa_text(f"SELECT {cols_sql} FROM {table}"))  # noqa: S608
        for row in result.fetchall():
            row_id = row[0]
            updates: dict[str, str] = {}
            for col, v in zip(columns, row[1:]):
                if v is None or v == "" or not isinstance(v, str):
                    continue
                try:
                    once = f.decrypt(v.encode("utf-8")).decode("utf-8")
                except InvalidToken:
                    # Not decryptable under our key — outside scope of
                    # this unwrap pass.
                    continue
                # If the once-decrypted value still looks like a Fernet
                # token AND decrypts under our key, the row was wrapped
                # twice. Replace with the once-decrypted (correctly-
                # single-encrypted) form.
                if once.startswith(_FERNET_PREFIX) and _is_decryptable(f, once):
                    updates[col] = once
                    stats["unwrapped"] += 1
                else:
                    stats["left_alone"] += 1
            if updates:
                set_sql = ", ".join(f"{col} = :{col}" for col in updates)
                params = {**updates, "row_id": row_id}
                await db.execute(
                    sa_text(f"UPDATE {table} SET {set_sql} WHERE id = :row_id"),
                    params,
                )
            stats["rows_checked"] += 1

    if stats["unwrapped"]:
        await db.commit()
        logger.info(
            "vault-field unwrap: rows_checked=%d unwrapped=%d left_alone=%d",
            stats["rows_checked"], stats["unwrapped"], stats["left_alone"],
        )
    return stats


async def count_legacy_field_rows(db: AsyncSession) -> int:
    """Count rows carrying at least one secret column that doesn't
    decrypt under the current key. Cheap probe used by the boot hook
    to decide whether to print the backfill banner."""
    f = _get_fernet()
    bad = 0
    for table, columns in _TABLE_SPECS:
        cols_sql = ", ".join(["id"] + list(columns))
        result = await db.execute(sa_text(f"SELECT {cols_sql} FROM {table}"))  # noqa: S608
        for row in result.fetchall():
            for value in row[1:]:
                if value is None or value == "" or not isinstance(value, str):
                    continue
                if not _is_decryptable(f, value):
                    bad += 1
                    break
    return bad


# Legacy alias for the pre-rewrite tests that imported the row-level
# helper directly. The new implementation is table-level (raw SQL is
# the cleanest way to bypass the EncryptedText column type), so
# call-sites that want per-row behaviour should use _walk_table on a
# bind-bound table. Kept as a no-op stub for import-time compatibility
# until the old tests are migrated.
def _backfill_row_fields(*_args, **_kwargs):  # pragma: no cover — see note above
    raise NotImplementedError(
        "_backfill_row_fields was removed when the backfill moved to raw SQL; "
        "use _walk_table or the public backfill_legacy_vault_fields helper."
    )


# Public re-export so tests can introspect the registry.
def _table_specs():  # pragma: no cover — passthrough
    return _TABLE_SPECS
