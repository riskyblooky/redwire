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

Usage (inside the backend container):
    docker compose exec backend python3 rotate_encryption_keys.py --dry-run
    docker compose exec backend python3 rotate_encryption_keys.py

Idempotent & resumable: each value is tried new-key-first (already migrated →
skip), then old-key (re-key), then treated as legacy plaintext (encrypt fresh).
"""
import argparse
import asyncio
import base64
import hashlib
import os
import sys

import asyncpg
from cryptography.fernet import Fernet, InvalidToken

# ── Tables/columns encrypted with the VAULT key ──
VAULT_DB_FIELDS = {
    "vault_items": ("username", "password", "note"),
    "infra_vault_items": ("username", "password", "note"),
    "spray_campaigns": ("password_used",),
    "spray_results": ("password",),
}
# MinIO-backed file columns (object key in column, Fernet-encrypted body)
VAULT_FILE_TABLES = ("vault_items", "infra_vault_items")
# ── Columns encrypted with the TOTP key ──
TOTP_DB_FIELDS = {"users": ("totp_secret",)}


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

    def line(self, label):
        return (f"  {label:28} rekeyed={self.rekeyed}  already-new={self.already}  "
                f"plaintext-encrypted={self.plaintext}  empty/skip={self.empty}")


def rekey_str(val, new_f: Fernet, old_f: Fernet, st: Stats):
    """Return new ciphertext str, or None if no change needed."""
    if val is None or val == "":
        st.empty += 1
        return None
    raw = val.encode()
    try:
        new_f.decrypt(raw)
        st.already += 1
        return None  # already under the new key
    except InvalidToken:
        pass
    try:
        pt = old_f.decrypt(raw)
        st.rekeyed += 1
        return new_f.encrypt(pt).decode()
    except InvalidToken:
        pass
    # Not decryptable by either key → legacy plaintext stored before encryption.
    st.plaintext += 1
    return new_f.encrypt(raw).decode()


def rekey_bytes(data: bytes, new_f: Fernet, old_f: Fernet, st: Stats):
    if not data:
        st.empty += 1
        return None
    try:
        new_f.decrypt(data)
        st.already += 1
        return None
    except InvalidToken:
        pass
    try:
        pt = old_f.decrypt(data)
        st.rekeyed += 1
        return new_f.encrypt(pt)
    except InvalidToken:
        pass
    st.plaintext += 1
    return new_f.encrypt(data)


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


async def migrate_db_fields(conn, fields_map, new_f, old_f, dry_run):
    for table, cols in fields_map.items():
        st = Stats()
        sel_cols = ", ".join(("id", *cols))
        rows = await conn.fetch(f"SELECT {sel_cols} FROM {table}")  # nosec: static table/col names
        for r in rows:
            updates = {}
            for col in cols:
                new_val = rekey_str(r[col], new_f, old_f, st)
                if new_val is not None:
                    updates[col] = new_val
            if updates and not dry_run:
                set_clause = ", ".join(f"{c} = ${i+2}" for i, c in enumerate(updates))
                await conn.execute(
                    f"UPDATE {table} SET {set_clause} WHERE id = $1",
                    r["id"], *updates.values())
        print(st.line(table))


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
        new_body = rekey_bytes(body, new_f, old_f, st)
        if new_body is not None and not dry_run:
            s3.put_object(Bucket=bucket, Key=key, Body=new_body)
    return st


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would change without writing")
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

    # MinIO files (vault key) — outside the DB transaction
    print("\nVault-key MinIO files:")
    for table in VAULT_FILE_TABLES:
        keys = [r["file_path"] for r in await conn.fetch(
            f"SELECT file_path FROM {table} WHERE file_path IS NOT NULL")]
        st = migrate_minio_files(keys, new_vault_f, old_vault_f, args.dry_run, bucket)
        print(st.line(f"{table} files"))

    await conn.close()
    print("\nDone." + ("  (dry run — nothing written)" if args.dry_run else ""))


class _Rollback(Exception):
    pass


if __name__ == "__main__":
    asyncio.run(main())
