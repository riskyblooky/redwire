"""SQLAlchemy column type that transparently encrypts at the ORM layer.

GHSA-3r7j-7h5r-gxgx follow-up — the structural counterpart to the
fail-closed ``decrypt_field`` flip. Routers used to wrap every write
through ``encrypt_field()`` / ``encrypt_vault_fields()``; one missed
callsite (the 3r7j-era import bug) wrote plaintext into the column
and stayed invisible because ``decrypt_field`` silently round-tripped
the raw value.

Pushing the crypt into the column type makes the bug shape impossible
to repeat: every write goes through ``process_bind_param`` regardless
of which router writes it, every read goes through
``process_result_value`` regardless of which router reads it. There is
no plaintext code path through the ORM.

Semantics:
  - ``None``     ⇄ ``None`` (no encryption, stored as NULL)
  - ``str``      ⇒ Fernet ciphertext on write; decrypted back to ``str``
    on read (or ``None`` if decryption fails — matches the fail-closed
    contract of ``decrypt_field``; the warning is emitted there).
  - non-``str`` writes are rejected so a future schema change that
    accidentally rebinds the column to an int / bytes / dict surfaces
    the type mismatch instead of silently storing garbage.

The Fernet key is read lazily through ``_get_fernet`` so a missing
``VAULT_ENCRYPTION_KEY`` env var crashes at the first write/read, not
at module import time (preserves the test-suite import shape).
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.types import TypeDecorator, Text

from utils.vault_crypto import decrypt_field, encrypt_field


class EncryptedText(TypeDecorator):
    """Text column whose values are Fernet-encrypted at rest.

    Drop-in replacement for ``Column(Text, ...)`` on any column that
    should hold a secret. No router code involved — the type does it.
    """

    impl = Text
    # No per-instance state — the encryption key comes from a global
    # env-backed singleton, so the SQLAlchemy query-compilation cache
    # can reuse compiled forms safely. Setting this False would
    # disable caching for every query that touches an encrypted column
    # and triggers a warning at compile time.
    cache_ok = True

    def process_bind_param(self, value: Optional[str], dialect) -> Optional[str]:
        if value is None:
            return None
        if not isinstance(value, str):
            # Reject early — silently coercing would mask a real bug
            # (e.g. a router passing a dict by mistake).
            raise TypeError(
                f"EncryptedText only accepts str | None, got {type(value).__name__}"
            )
        return encrypt_field(value)

    def process_result_value(self, value: Optional[str], dialect) -> Optional[str]:
        if value is None:
            return None
        return decrypt_field(value)
