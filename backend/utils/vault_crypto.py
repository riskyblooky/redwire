"""
Vault field-level encryption using Fernet (AES-128-CBC + HMAC-SHA256).

Every sensitive vault field (username, password, note) is encrypted before
being persisted to PostgreSQL and decrypted when read back.

Key is sourced exclusively from the VAULT_ENCRYPTION_KEY env var, which must be
a valid Fernet key (32 url-safe base64-encoded bytes, as produced by
`Fernet.generate_key()`). The module fails closed: if the key is absent or
malformed it raises rather than deriving a key from any other secret.
"""

import os
import binascii
import logging
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

_ENCRYPTION_KEY: Optional[str] = None

_KEYGEN_HINT = (
    "Generate one with: "
    "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
)


def _get_fernet() -> Fernet:
    """Return a cached Fernet instance, initialising the key on first call.

    Fails closed: VAULT_ENCRYPTION_KEY must be set and be a valid Fernet key.
    No fallback derivation from JWT_SECRET (GHSA-pg99-33rm-7wgq)."""
    global _ENCRYPTION_KEY

    if _ENCRYPTION_KEY is None:
        raw = os.getenv("VAULT_ENCRYPTION_KEY", "").strip()
        if not raw:
            raise RuntimeError(
                "VAULT_ENCRYPTION_KEY is not set. Refusing to derive a vault "
                f"encryption key from JWT_SECRET. {_KEYGEN_HINT}"
            )
        try:
            Fernet(raw)  # validates url-safe base64 / 32-byte length
        except (ValueError, binascii.Error, TypeError) as e:
            raise RuntimeError(
                "VAULT_ENCRYPTION_KEY is not a valid Fernet key (must be 32 "
                f"url-safe base64-encoded bytes). {_KEYGEN_HINT}"
            ) from e
        _ENCRYPTION_KEY = raw

    return Fernet(_ENCRYPTION_KEY)


def validate_key() -> None:
    """Force key validation (used at startup to fail closed early)."""
    _get_fernet()


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


def encrypt_bytes(data: bytes) -> bytes:
    """Encrypt arbitrary binary content for storage (e.g. vault file uploads).

    Returns base64-url Fernet ciphertext as bytes. Use ``decrypt_bytes`` on
    read; it falls back to the raw input for legacy plaintext files that
    were stored before vault-file encryption shipped (RDW-057).
    """
    if data is None:
        return data
    f = _get_fernet()
    return f.encrypt(data)


def decrypt_bytes(data: bytes) -> bytes:
    """Decrypt vault file bytes. Falls back to the raw input for legacy
    plaintext files (any file uploaded before RDW-057 shipped). Without
    the fallback every pre-fix download would 500."""
    if data is None:
        return data
    try:
        f = _get_fernet()
        return f.decrypt(data)
    except (InvalidToken, Exception):
        return data


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
