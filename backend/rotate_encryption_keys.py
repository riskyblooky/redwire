#!/usr/bin/env python3
"""
rotate_encryption_keys.py — GHSA-pg99-33rm-7wgq

Re-encrypts every at-rest secret onto new dedicated Fernet keys. Supports
two modes via env vars:

  (a) PG99 MIGRATION (no OLD_*_ENCRYPTION_KEY set) — the original use case:
      derive the OLD keys from JWT_SECRET (the legacy fallback formulas) and
      re-key onto the new VAULT_ENCRYPTION_KEY / TOTP_ENCRYPTION_KEY.

  (b) DEDICATED-TO-DEDICATED ROTATION (OLD_*_ENCRYPTION_KEY set) — for
      operators who want to rotate already-set dedicated keys (e.g. periodic
      rotation, suspected key exposure). Pass the CURRENT keys as
      OLD_VAULT_ENCRYPTION_KEY / OLD_TOTP_ENCRYPTION_KEY and the new keys as
      VAULT_ENCRYPTION_KEY / TOTP_ENCRYPTION_KEY. JWT_SECRET is not consulted.

Run order on an upgrade or rotation:
  1. Back up Postgres AND MinIO.
  2. Generate new keys: python3 scripts/generate_encryption_keys.py
  3. Set the new keys in the environment (VAULT_ENCRYPTION_KEY,
     TOTP_ENCRYPTION_KEY). For mode (b), also set OLD_VAULT_ENCRYPTION_KEY
     and OLD_TOTP_ENCRYPTION_KEY to the keys currently in use.
  4. Run this script.
  5. Deploy the fail-closed backend.

For mode (a), do NOT rotate JWT_SECRET until this has completed — the old
key is unrecoverable once JWT_SECRET changes.

Usage — with the backend STOPPED (a running backend keeps writing under the
old key, and those rows would be unreadable afterwards), in a one-off
container so the keys can be passed in:

    docker compose stop backend
    docker compose run --rm \
      -e OLD_VAULT_ENCRYPTION_KEY=<current> -e OLD_TOTP_ENCRYPTION_KEY=<current> \
      -e VAULT_ENCRYPTION_KEY=<new>         -e TOTP_ENCRYPTION_KEY=<new> \
      backend python3 rotate_encryption_keys.py --dry-run
    # ... then without --dry-run, then put the new keys in .env and
    docker compose up -d backend     # `restart` would keep the old env

Idempotent & resumable: each value is tried new-key-first (already migrated →
skip), then old-key (re-key). A value that is not a Fernet token is legacy
plaintext and gets encrypted. A value that IS a Fernet token but opens under
neither key is left untouched and reported — that means a wrong old key, and
wrapping it again would bury the secret under two layers. A preflight pass
(no writes) runs first; if it finds any such value the run stops before
writing anything, unless --allow-undecryptable is given.
"""
import argparse
import asyncio
import base64
import hashlib
import os
import sys

import asyncpg
from cryptography.fernet import Fernet, InvalidToken

# ── Tables/columns encrypted with the VAULT key: table → (primary key, columns).
# Every EncryptedText column must be here (tests/test_rotate_encryption_keys.py
# checks the models against this map).
VAULT_DB_FIELDS = {
    "vault_items": ("id", ("username", "password", "note")),
    "infra_vault_items": ("id", ("username", "password", "note")),
    "spray_campaigns": ("id", ("password_used",)),
    "spray_results": ("id", ("username", "password")),
    "auth_settings": ("key", ("value",)),
    "plugin_settings": ("id", ("value",)),
}
# MinIO-backed file columns (object key in column, Fernet-encrypted body)
VAULT_FILE_TABLES = ("vault_items", "infra_vault_items")
# ── Columns encrypted with the TOTP key ──
TOTP_DB_FIELDS = {"users": ("id", ("totp_secret",))}


def looks_like_fernet(raw: bytes) -> bool:
    """A Fernet token is url-safe base64 of version byte 0x80 + 8-byte
    timestamp + 16-byte IV + ≥16-byte ciphertext + 32-byte HMAC."""
    try:
        data = base64.urlsafe_b64decode(raw)
    except Exception:
        return False
    return len(data) >= 73 and data[0] == 0x80


def _legacy_vault_key(secret: str) -> bytes:
    return base64.urlsafe_b64encode(hashlib.sha256(f"vault-key:{secret}".encode()).digest())


def _legacy_totp_key(secret: str) -> bytes:
    return base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())


class Stats:
    def __init__(self):
        self.rekeyed = 0
        self.already = 0
        self.plaintext = 0
        self.empty = 0
        self.undecryptable: list[str] = []   # "table.column pk=…" / "object key"

    def line(self, label):
        return (f"  {label:28} rekeyed={self.rekeyed}  already-new={self.already}  "
                f"plaintext-encrypted={self.plaintext}  empty/skip={self.empty}  "
                f"UNDECRYPTABLE={len(self.undecryptable)}")


def rekey_bytes(data: bytes, new_f: Fernet, old_f: Fernet, st: Stats, where: str = ""):
    """Return new ciphertext bytes, or None if nothing should be written."""
    if not data:
        st.empty += 1
        return None
    try:
        new_f.decrypt(data)
        st.already += 1
        return None  # already under the new key
    except InvalidToken:
        pass
    try:
        pt = old_f.decrypt(data)
        st.rekeyed += 1
        return new_f.encrypt(pt)
    except InvalidToken:
        pass
    if looks_like_fernet(data):
        # Ciphertext under some third key (almost always: the wrong OLD key
        # was supplied). Leave it alone — re-encrypting it as if it were
        # plaintext would make the secret unrecoverable with either key.
        st.undecryptable.append(where)
        return None
    # Not a token at all → legacy plaintext stored before encryption.
    st.plaintext += 1
    return new_f.encrypt(data)


def rekey_str(val, new_f: Fernet, old_f: Fernet, st: Stats, where: str = ""):
    """Return new ciphertext str, or None if no change needed."""
    if val is None or val == "":
        st.empty += 1
        return None
    out = rekey_bytes(val.encode(), new_f, old_f, st, where)
    return out.decode() if out is not None else None


def _s3_client():
    import boto3
    endpoint = os.getenv("MINIO_ENDPOINT", "minio:9000")
    secure = os.getenv("MINIO_SECURE", "false").lower() == "true"
    return boto3.client(
        "s3",
        endpoint_url=f"{'https' if secure else 'http'}://{endpoint}",
        aws_access_key_id=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
        aws_secret_access_key=os.getenv("MINIO_SECRET_KEY", "minioadmin"),
        region_name="us-east-1",
    )


async def migrate_db_fields(conn, fields_map, new_f, old_f, dry_run, quiet=False) -> list[str]:
    """Re-key every listed column. Returns the undecryptable locations."""
    bad: list[str] = []
    for table, (pk, cols) in fields_map.items():
        st = Stats()
        sel_cols = ", ".join((pk, *cols))
        rows = await conn.fetch(f"SELECT {sel_cols} FROM {table}")  # nosec: static table/col names
        for r in rows:
            updates = {}
            for col in cols:
                new_val = rekey_str(r[col], new_f, old_f, st, f"{table}.{col} {pk}={r[pk]}")
                if new_val is not None:
                    updates[col] = new_val
            if updates and not dry_run:
                set_clause = ", ".join(f"{c} = ${i+2}" for i, c in enumerate(updates))
                await conn.execute(
                    f"UPDATE {table} SET {set_clause} WHERE {pk} = $1",
                    r[pk], *updates.values())
        if not quiet:
            print(st.line(table))
        bad.extend(st.undecryptable)
    return bad


def migrate_minio_files(conn_rows, new_f, old_f, dry_run, bucket):
    """conn_rows: list of object keys. Returns Stats."""
    st = Stats()
    if not conn_rows:
        return st
    s3 = _s3_client()
    for key in conn_rows:
        if not key:
            st.empty += 1
            continue
        try:
            body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
        except Exception as e:
            print(f"    ! could not read object {key}: {e}")
            continue
        new_body = rekey_bytes(body, new_f, old_f, st, f"object {key}")
        if new_body is not None and not dry_run:
            s3.put_object(Bucket=bucket, Key=key, Body=new_body)
    return st


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would change without writing")
    ap.add_argument("--allow-undecryptable", action="store_true",
                    help="write even if some ciphertext opens under neither key "
                         "(those values are left untouched)")
    args = ap.parse_args()

    # OLD keys: explicit env override takes precedence (dedicated->dedicated
    # rotation), else fall back to deriving from JWT_SECRET (pg99 first-time
    # migration). At least one path must yield a key, or we can't read existing
    # data.
    explicit_old_vault = os.getenv("OLD_VAULT_ENCRYPTION_KEY", "").strip()
    explicit_old_totp = os.getenv("OLD_TOTP_ENCRYPTION_KEY", "").strip()
    jwt_secret = os.getenv("JWT_SECRET", "")
    if not (explicit_old_vault or jwt_secret):
        sys.exit(
            "Neither OLD_VAULT_ENCRYPTION_KEY nor JWT_SECRET is set — "
            "no way to read existing vault data.")
    if not (explicit_old_totp or jwt_secret):
        sys.exit(
            "Neither OLD_TOTP_ENCRYPTION_KEY nor JWT_SECRET is set — "
            "no way to read existing TOTP data.")

    new_vault = os.getenv("VAULT_ENCRYPTION_KEY", "").strip()
    new_totp = os.getenv("TOTP_ENCRYPTION_KEY", "").strip()

    if not args.dry_run:
        missing = [n for n, v in (("VAULT_ENCRYPTION_KEY", new_vault),
                                  ("TOTP_ENCRYPTION_KEY", new_totp)) if not v]
        if missing:
            sys.exit(
                f"{', '.join(missing)} not set. Set the dedicated key(s) in the "
                "environment before a real run so the new ciphertext is readable "
                "by the app. (Use --dry-run to preview without keys.)")
    else:
        # Preview mode may run without dedicated keys; synthesise samples.
        if not new_vault:
            new_vault = Fernet.generate_key().decode()
            print(f"[dry-run] sample VAULT_ENCRYPTION_KEY = {new_vault}")
        if not new_totp:
            new_totp = Fernet.generate_key().decode()
            print(f"[dry-run] sample TOTP_ENCRYPTION_KEY  = {new_totp}")

    try:
        new_vault_f = Fernet(new_vault)
        new_totp_f = Fernet(new_totp)
    except Exception as e:
        sys.exit(f"Provided key is not a valid Fernet key: {e}")

    try:
        old_vault_f = Fernet(explicit_old_vault) if explicit_old_vault else Fernet(_legacy_vault_key(jwt_secret))
        old_totp_f = Fernet(explicit_old_totp) if explicit_old_totp else Fernet(_legacy_totp_key(jwt_secret))
    except Exception as e:
        sys.exit(f"OLD_*_ENCRYPTION_KEY env var is not a valid Fernet key: {e}")

    vault_src = "OLD_VAULT_ENCRYPTION_KEY" if explicit_old_vault else "derived from JWT_SECRET"
    totp_src = "OLD_TOTP_ENCRYPTION_KEY"  if explicit_old_totp  else "derived from JWT_SECRET"
    print(f"  vault old key: {vault_src}")
    print(f"  totp  old key: {totp_src}")

    dsn = os.getenv("DATABASE_URL", "").replace("postgresql+asyncpg://", "postgresql://")
    bucket = os.getenv("MINIO_BUCKET", "redwire-evidence")

    mode = "DRY RUN (no writes)" if args.dry_run else "LIVE (rewriting data)"
    print("=" * 70)
    print(f"GHSA-pg99 key rotation — {mode}")
    print("=" * 70)

    conn = await asyncpg.connect(dsn)
    file_keys = {}
    for table in VAULT_FILE_TABLES:
        file_keys[table] = [r["file_path"] for r in await conn.fetch(
            f"SELECT file_path FROM {table} WHERE file_path IS NOT NULL")]

    # Preflight: read everything, write nothing. A Fernet token that opens
    # under neither key means the OLD key is wrong — stop before touching
    # anything (MinIO writes can't be rolled back with the DB).
    bad = await migrate_db_fields(conn, VAULT_DB_FIELDS, new_vault_f, old_vault_f, True, quiet=True)
    bad += await migrate_db_fields(conn, TOTP_DB_FIELDS, new_totp_f, old_totp_f, True, quiet=True)
    for table, keys in file_keys.items():
        bad += migrate_minio_files(keys, new_vault_f, old_vault_f, True, bucket).undecryptable
    if bad:
        print(f"\n{len(bad)} value(s) are Fernet ciphertext that opens under NEITHER the old nor the new key:")
        for where in bad[:20]:
            print(f"    {where}")
        if len(bad) > 20:
            print(f"    … and {len(bad) - 20} more")
        print("The OLD_*_ENCRYPTION_KEY (or JWT_SECRET) supplied is probably not the key the data was")
        print("written with. Nothing has been written.")
        if not args.dry_run and not args.allow_undecryptable:
            await conn.close()
            sys.exit("Aborting. Fix the old key, or pass --allow-undecryptable to re-key the rest "
                     "and leave these values as they are.")

    try:
        async with conn.transaction():
            print("\nVault-key DB fields:")
            await migrate_db_fields(conn, VAULT_DB_FIELDS, new_vault_f, old_vault_f, args.dry_run)
            print("\nTOTP-key DB fields:")
            await migrate_db_fields(conn, TOTP_DB_FIELDS, new_totp_f, old_totp_f, args.dry_run)
            if args.dry_run:
                raise _Rollback()  # abort the transaction cleanly in dry-run
    except _Rollback:
        pass

    # MinIO files (vault key) — outside the DB transaction. Safe to re-run if
    # this part is interrupted: re-keyed objects are skipped as already-new.
    print("\nVault-key MinIO files:")
    for table, keys in file_keys.items():
        st = migrate_minio_files(keys, new_vault_f, old_vault_f, args.dry_run, bucket)
        print(st.line(f"{table} files"))

    await conn.close()
    print("\nDone." + ("  (dry run — nothing written)" if args.dry_run else ""))


class _Rollback(Exception):
    pass


if __name__ == "__main__":
    asyncio.run(main())
