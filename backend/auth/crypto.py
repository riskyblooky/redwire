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


def decrypt_totp_secret(stored):
    """Decrypt a TOTP secret from the database.

    GHSA-rp23-74j3-mqmq: fail-closed. Returns ``None`` on any value
    that is not a Fernet ciphertext decryptable under the current
    TOTP_ENCRYPTION_KEY — including legacy plaintext left behind by
    the pre-2026-02-20 storage rollout. The previous behaviour was
    to return the raw value on both the "no gAAAAA prefix" (legacy
    plaintext) branch and the InvalidToken branch, so legacy TOTP
    seeds continued to work through the API and the at-rest
    encryption guarantee silently did not apply to them.

    The boot-time ``backfill_legacy_totp_secrets`` helper walks
    ``users`` and re-encrypts any legacy plaintext seed before this
    fail-closed path can affect it on an upgrade. Wrong-key
    ciphertext (Fernet-shaped but not decryptable under our key —
    restored backup / rotated key) also returns ``None`` so an
    operator notices the mismatch rather than the seed silently
    round-tripping.

    Callers that read ``user.totp_secret`` and see ``None`` here
    should treat the row as missing a valid seed — the 2FA verify
    will correctly refuse, forcing re-enrollment.
    """
    from cryptography.fernet import InvalidToken
    if not stored:
        return stored
    try:
        f = _get_fernet()
        return f.decrypt(stored.encode()).decode()
    except InvalidToken:
        logger.warning(
            "decrypt_totp_secret: InvalidToken — value is not decryptable "
            "under the current TOTP_ENCRYPTION_KEY. Returning None. "
            "Investigate legacy plaintext (backfill should have caught "
            "this) / wrong-key / restored-backup / corruption."
        )
        return None
