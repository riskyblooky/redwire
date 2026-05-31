#!/usr/bin/env python3
"""
Generate fresh Fernet encryption keys for VAULT_ENCRYPTION_KEY and
TOTP_ENCRYPTION_KEY, formatted for paste-into-.env.

Use this when:
  - Setting up a new RedWire deployment (instead of relying on the docker-compose
    dev defaults — which are baked-in for first-run convenience but should be
    replaced for anything beyond local development).
  - You want your own keys instead of the public dev defaults.

For ROTATING existing keys (re-encrypting at-rest data onto fresh keys), see
backend/rotate_encryption_keys.py — that script handles the data migration.

Usage:
    python3 scripts/generate_encryption_keys.py             # print key=value lines
    python3 scripts/generate_encryption_keys.py >> .env     # append to .env

Stdlib only — no extra dependencies on the host.
"""
import base64
import os
import sys
from datetime import datetime, timezone


def _fernet_key() -> str:
    """Return a 32-byte url-safe base64 Fernet key. Matches the format the
    cryptography library expects."""
    return base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")


def main() -> int:
    vault = _fernet_key()
    totp = _fernet_key()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"# RedWire encryption keys — generated {ts}")
    print("# Save these somewhere durable (password manager). Losing them means")
    print("# losing all vault credentials and TOTP seeds; there is no recovery.")
    print(f"VAULT_ENCRYPTION_KEY={vault}")
    print(f"TOTP_ENCRYPTION_KEY={totp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
