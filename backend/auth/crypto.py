"""
Symmetric encryption helpers for sensitive data at rest.

Uses Fernet (AES-128-CBC + HMAC-SHA256) from the `cryptography` package.
The encryption key is derived from the TOTP_ENCRYPTION_KEY environment variable.
If no key is set, falls back to a deterministic key derived from JWT_SECRET
(not ideal, but prevents startup failures).
"""
import os
import base64
import hashlib
import logging

logger = logging.getLogger(__name__)

_fernet = None


def _get_fernet():
    """Lazily initialise the Fernet instance."""
    global _fernet
    if _fernet is not None:
        return _fernet

    from cryptography.fernet import Fernet

    key = os.getenv("TOTP_ENCRYPTION_KEY", "")
    if not key:
        # Derive a Fernet-compatible key from JWT_SECRET as fallback
        jwt_secret = os.getenv("JWT_SECRET", "your-secret-key-change-in-production")
        raw = hashlib.sha256(jwt_secret.encode()).digest()
        key = base64.urlsafe_b64encode(raw).decode()
        logger.warning(
            "TOTP_ENCRYPTION_KEY not set — deriving from JWT_SECRET. "
            "Set TOTP_ENCRYPTION_KEY for production."
        )

    _fernet = Fernet(key)
    return _fernet


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
