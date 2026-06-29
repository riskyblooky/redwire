"""EncryptedText column-type regressions.

GHSA-3r7j-7h5r-gxgx follow-up. ``EncryptedText`` is a SQLAlchemy
``TypeDecorator`` that wraps the existing Fernet helpers and applies
them transparently at bind / result time — every write through any
router that touches a vault secret column gets Fernet-encrypted at the
ORM layer, every read gets decrypted before the router ever sees the
value. The motivation is structural: the 3r7j-era plaintext leak
happened because one write path forgot to call ``encrypt_field``;
pushing the crypt into the column type makes that bug shape
impossible to repeat.

These tests pin the bind / result contract in pure Python (no DB
required) — the cryptographic round-trip, the None pass-through, the
fail-closed inheritance from ``decrypt_field``, and the type guard
against non-str writes.
"""

from __future__ import annotations

import os

import pytest
from cryptography.fernet import Fernet

# Ensure a vault key is present before importing the type.
os.environ.setdefault("VAULT_ENCRYPTION_KEY", Fernet.generate_key().decode())

from utils.encrypted_types import EncryptedText
from utils.vault_crypto import _get_fernet


@pytest.fixture
def col():
    return EncryptedText()


# ── process_bind_param: write side ───────────────────────────────────


class TestProcessBindParam:
    """Encrypt-on-write. Routers hand in plaintext str (or None); the
    type emits Fernet ciphertext (or None) to the DB driver."""

    def test_none_passes_through(self, col):
        # ``None`` → ``None`` so nullable columns stay queryable for
        # IS NULL / IS NOT NULL filters at the SQL layer.
        assert col.process_bind_param(None, None) is None

    def test_str_encrypted(self, col):
        ct = col.process_bind_param("secret", None)
        assert ct is not None
        # Result is a real Fernet token — round-trips under our key.
        assert _get_fernet().decrypt(ct.encode("utf-8")) == b"secret"

    def test_empty_string_encrypted(self, col):
        # Empty string is still a valid plaintext value; encrypt it so
        # the column round-trips. Important for upstream code that
        # treats "" as "explicit empty" rather than "missing".
        ct = col.process_bind_param("", None)
        assert _get_fernet().decrypt(ct.encode("utf-8")) == b""

    def test_non_str_rejected(self, col):
        # Silent coercion would hide a real bug (e.g. a router passing
        # a dict). Surface the type mismatch with a TypeError.
        for bad in (123, b"bytes", [], {}, 1.5):
            with pytest.raises(TypeError, match="str | None"):
                col.process_bind_param(bad, None)

    def test_each_encryption_uses_fresh_iv(self, col):
        # Sanity check on the underlying Fernet impl — encrypting the
        # same plaintext twice MUST yield different ciphertext (random
        # IV per call). Pin so a hypothetical "cache ciphertext" perf
        # tweak somewhere upstream can't slip in undetected.
        a = col.process_bind_param("same", None)
        b = col.process_bind_param("same", None)
        assert a != b


# ── process_result_value: read side ──────────────────────────────────


class TestProcessResultValue:
    """Decrypt-on-read. The DB driver hands in the stored ciphertext;
    the type emits plaintext str (or None) to the ORM. Inherits the
    fail-closed contract from ``decrypt_field``."""

    def test_none_passes_through(self, col):
        assert col.process_result_value(None, None) is None

    def test_valid_ciphertext_decrypted(self, col):
        f = _get_fernet()
        ct = f.encrypt(b"hello").decode("utf-8")
        assert col.process_result_value(ct, None) == "hello"

    def test_garbage_returns_none(self, col):
        # InvalidToken on read → None (fail-closed). Pre-flip behaviour
        # was to round-trip the raw value, which was the whole bug
        # decrypt_field was hiding.
        assert col.process_result_value("not a token", None) is None

    def test_wrong_key_ciphertext_returns_none(self, col):
        foreign = Fernet(Fernet.generate_key())
        ct = foreign.encrypt(b"sensitive").decode("utf-8")
        assert col.process_result_value(ct, None) is None


# ── end-to-end round-trip ────────────────────────────────────────────


class TestRoundTrip:
    """The contract callers actually depend on: write a str, read the
    same str back through the bind → result pair."""

    def test_str_roundtrip(self, col):
        original = "P@ssw0rd! ÿ unicode \U0001f512"
        stored = col.process_bind_param(original, None)
        recovered = col.process_result_value(stored, None)
        assert recovered == original

    def test_none_roundtrip(self, col):
        stored = col.process_bind_param(None, None)
        assert stored is None
        recovered = col.process_result_value(stored, None)
        assert recovered is None

    def test_empty_string_roundtrip(self, col):
        stored = col.process_bind_param("", None)
        recovered = col.process_result_value(stored, None)
        assert recovered == ""


# ── cache_ok flag ────────────────────────────────────────────────────


class TestCacheOk:
    """``cache_ok = True`` is required for the SQLAlchemy query-
    compilation cache to reuse compiled statements that touch this
    column type. Setting it False would print a warning at every query
    compile that mentions an encrypted column."""

    def test_cache_ok_true(self):
        # Class-level attr, not instance. Pin so a future maintainer
        # can't accidentally flip it.
        assert EncryptedText.cache_ok is True
