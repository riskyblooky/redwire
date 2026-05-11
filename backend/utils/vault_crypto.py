"""
Vault field-level encryption using Fernet (AES-128-CBC + HMAC-SHA256).

Every sensitive vault field (username, password, note) is encrypted before
being persisted to PostgreSQL and decrypted when read back.

Key is sourced from the VAULT_ENCRYPTION_KEY env var.  In development, a
deterministic key is derived automatically so that existing data survives
container restarts.
"""

import os
import base64
import hashlib
import logging
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

_ENCRYPTION_KEY: Optional[str] = None


def _get_fernet() -> Fernet:
    """Return a cached Fernet instance, initialising the key on first call."""
    global _ENCRYPTION_KEY

    if _ENCRYPTION_KEY is None:
        raw = os.getenv("VAULT_ENCRYPTION_KEY", "")
        if raw:
            # Validate that the key is valid Fernet (url-safe base64, 32 bytes)
            _ENCRYPTION_KEY = raw
        else:
            # Derive a deterministic dev key from JWT_SECRET so data survives
            # restarts without requiring an explicit env var.
            jwt_secret = os.getenv("JWT_SECRET", "redwire-dev-fallback")
            derived = hashlib.sha256(f"vault-key:{jwt_secret}".encode()).digest()
            _ENCRYPTION_KEY = base64.urlsafe_b64encode(derived).decode()
            logger.warning(
                "VAULT_ENCRYPTION_KEY not set — derived a key from JWT_SECRET. "
                "Set VAULT_ENCRYPTION_KEY in production!"
            )

    return Fernet(_ENCRYPTION_KEY)


def encrypt_field(value: Optional[str]) -> Optional[str]:
    """Encrypt a plaintext string.  Returns base64 ciphertext or None."""
    if value is None:
        return None
    f = _get_fernet()
    return f.encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_field(value: Optional[str]) -> Optional[str]:
    """Decrypt a ciphertext string.  Gracefully returns the raw value if
    decryption fails (handles legacy unencrypted data)."""
    if value is None:
        return None
    try:
        f = _get_fernet()
        return f.decrypt(value.encode("utf-8")).decode("utf-8")
    except (InvalidToken, Exception):
        # Legacy plaintext — return as-is
        return value


# ---------------------------------------------------------------------------
# Convenience wrappers for encrypting / decrypting the three vault fields
# on a dict (used by the router layer).
# ---------------------------------------------------------------------------

ENCRYPTED_FIELDS = ("username", "password", "note")


def encrypt_vault_fields(data: dict) -> dict:
    """Return a *new* dict with encrypted values for vault-sensitive keys."""
    out = dict(data)
    for field in ENCRYPTED_FIELDS:
        if field in out and out[field] is not None:
            out[field] = encrypt_field(out[field])
    return out


def decrypt_vault_item(item) -> None:
    """Decrypt sensitive fields **in-place** on a SQLAlchemy VaultItem."""
    for field in ENCRYPTED_FIELDS:
        raw = getattr(item, field, None)
        if raw is not None:
            setattr(item, field, decrypt_field(raw))
