"""
Symmetric encryption helpers for sensitive data at rest.

Uses Fernet (AES-128-CBC + HMAC-SHA256) from the `cryptography` package.
The encryption key is sourced exclusively from the TOTP_ENCRYPTION_KEY
environment variable, which must be a valid Fernet key. The module fails
closed: if the key is absent or malformed it raises rather than deriving a
key from JWT_SECRET (GHSA-pg99-33rm-7wgq).
"""
import os
import binascii
import logging

logger = logging.getLogger(__name__)

_fernet = None

_KEYGEN_HINT = (
    "Generate one with: "
    "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
)


def _get_fernet():
    """Lazily initialise the Fernet instance, failing closed on a missing or
    malformed TOTP_ENCRYPTION_KEY."""
    global _fernet
    if _fernet is not None:
        return _fernet

    from cryptography.fernet import Fernet

    key = os.getenv("TOTP_ENCRYPTION_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "TOTP_ENCRYPTION_KEY is not set. Refusing to derive a TOTP "
            f"encryption key from JWT_SECRET. {_KEYGEN_HINT}"
        )
    try:
        _fernet = Fernet(key)  # validates url-safe base64 / 32-byte length
    except (ValueError, binascii.Error, TypeError) as e:
        raise RuntimeError(
            "TOTP_ENCRYPTION_KEY is not a valid Fernet key (must be 32 "
            f"url-safe base64-encoded bytes). {_KEYGEN_HINT}"
        ) from e
    return _fernet


def validate_key() -> None:
    """Force key validation (used at startup to fail closed early)."""
    _get_fernet()


def encrypt_totp_secret(plaintext: str) -> str:
    """Encrypt a TOTP secret for database storage."""
    f = _get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt_totp_secret(stored: str) -> str:
    """Decrypt a TOTP secret from the database.

    Handles backward compatibility: if the value doesn't look like a
    Fernet token (no 'gAAAAA' prefix), it's returned as-is (legacy
    plaintext secret).
    """
    if not stored:
        return stored

    # Fernet tokens always start with 'gAAAAA' (base64 of version byte 0x80)
    if not stored.startswith("gAAAAA"):
        return stored  # legacy plaintext — still works

    try:
        f = _get_fernet()
        return f.decrypt(stored.encode()).decode()
    except Exception:
        logger.error("Failed to decrypt TOTP secret — returning raw value")
        return stored
