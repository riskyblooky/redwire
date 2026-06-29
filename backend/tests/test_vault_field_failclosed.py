"""Vault-field fail-closed + legacy-plaintext backfill regressions.

GHSA-3r7j-7h5r-gxgx follow-up. ``decrypt_field`` now fails closed —
returns ``None`` + logs a warning on ``InvalidToken`` instead of
silently round-tripping the raw value. The backfill helper in
``vault_field_migration`` makes that flip safe on upgrade by
re-encrypting any legacy plaintext column values in place via raw SQL
(bypassing the EncryptedText column type that would otherwise
interfere).

These tests pin the pure-Python pieces that are load-bearing for
correctness — the cryptographic boundary of decrypt_field, the
registry that the backfill walks, and the helper functions. The
actual table-walk is exercised by the live boot-time smoke documented
in the commit message (it ran cleanly against the dev DB: 49 fields
encrypted across 47 rows from the 3r7j-era plaintext leak).
"""

from __future__ import annotations

import logging
import os

import pytest
from cryptography.fernet import Fernet

# Make sure a key is available before importing vault_crypto.
os.environ.setdefault("VAULT_ENCRYPTION_KEY", Fernet.generate_key().decode())

from utils.vault_crypto import decrypt_field, encrypt_field
from utils.vault_field_migration import (
    _FERNET_PREFIX,
    _is_decryptable,
    _table_specs,
)
from utils.vault_crypto import _get_fernet


# ── decrypt_field: fail-closed contract ──────────────────────────────


class TestDecryptFieldFailClosed:
    """The whole point of the change. Old behaviour was to round-trip
    the raw value on InvalidToken so the vault UI silently confirmed
    bad state. New behaviour: return None + log."""

    def test_roundtrip_still_works(self):
        ct = encrypt_field("secret-password")
        assert decrypt_field(ct) == "secret-password"

    def test_none_passes_through(self):
        # ``None`` always passes — same as the old behaviour. The fail-
        # closed flip is only for values that *exist* but can't be
        # decrypted.
        assert decrypt_field(None) is None

    def test_invalid_token_returns_none(self):
        # Pre-flip this would have returned "not actually a token".
        assert decrypt_field("not actually a token") is None

    def test_empty_string_returns_none(self):
        # Empty string isn't a valid Fernet token; pre-flip it would
        # have been round-tripped as "". Post-flip: None.
        assert decrypt_field("") is None

    def test_wrong_key_ciphertext_returns_none(self):
        # Encrypt under a foreign key, then try to decrypt under our key.
        # Pre-flip: returned the foreign ciphertext as if it were
        # plaintext. Post-flip: None.
        foreign = Fernet(Fernet.generate_key())
        ct = foreign.encrypt(b"x" * 32).decode("utf-8")
        assert decrypt_field(ct) is None

    def test_invalid_token_emits_warning(self, caplog):
        # The log message is the operator's signal that something is
        # wrong. Pin its presence so a future refactor can't silently
        # drop the only telemetry for this failure mode.
        with caplog.at_level(logging.WARNING, logger="utils.vault_crypto"):
            decrypt_field("garbage")
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert any("InvalidToken" in r.message for r in warnings)


# ── _is_decryptable: pure-logic helper ───────────────────────────────


class TestIsDecryptable:
    """The decision boundary inside the backfill — every per-column
    branch routes through this helper, so its contract is what
    determines whether a legacy plaintext row gets re-encrypted vs
    skipped vs left untouched."""

    def setup_method(self):
        from utils.vault_crypto import _get_fernet
        self.f = _get_fernet()

    def test_valid_ciphertext_true(self):
        ct = encrypt_field("hello")
        assert _is_decryptable(self.f, ct) is True

    def test_plaintext_false(self):
        # The legacy case the backfill exists to detect.
        assert _is_decryptable(self.f, "plain-text") is False

    def test_wrong_keyed_ciphertext_false(self):
        # `gAAAAA` prefix but encrypted under a foreign key — must read
        # as "not decryptable" so the wrong-keyed-Fernet branch in
        # the backfill engages (skip, not wrap).
        foreign = Fernet(Fernet.generate_key())
        ct = foreign.encrypt(b"sensitive").decode("utf-8")
        assert _is_decryptable(self.f, ct) is False


# ── _table_specs: the registry the backfill walks ─────────────────────


class TestTableSpecs:
    """``_table_specs`` is the registry of every (table, columns) pair
    the backfill operates on. If a new vault-encrypted table ever gets
    added elsewhere in the codebase, the corresponding entry must
    land here or the backfill will miss it — pin the current set so
    the failure mode is a noisy test failure, not a silent gap."""

    def test_expected_tables_present(self):
        specs = _table_specs()
        as_dict = {table: cols for table, cols in specs}
        assert as_dict == {
            "vault_items": ("username", "password", "note"),
            "infra_vault_items": ("username", "password", "note"),
            "spray_campaigns": ("password_used",),
            "spray_results": ("username", "password"),
        }

    def test_specs_are_strings_not_models(self):
        # The backfill uses raw SQL (sa.text), so it operates on string
        # table names. Going through ORM models would route through
        # the EncryptedText column type and break the migration
        # semantics (encrypt-on-bind would wrap any in-place fix in a
        # second layer). Pin the type so a future refactor doesn't
        # accidentally swap back to model classes.
        for table, columns in _table_specs():
            assert isinstance(table, str)
            assert isinstance(columns, tuple)
            assert all(isinstance(c, str) for c in columns)


# ── _FERNET_PREFIX: framing constant ─────────────────────────────────


class TestDoubleEncryptionDetection:
    """The unwrap helper distinguishes single-encrypted (decrypt-once →
    plaintext) from double-encrypted (decrypt-once → another Fernet
    token). Pin the pure detection logic that drives that branching."""

    def setup_method(self):
        self.f = _get_fernet()

    def test_single_decrypts_to_plaintext(self):
        # Single layer: decrypt-once → plaintext that does NOT look
        # like a Fernet token → leave alone.
        ct = self.f.encrypt(b"hello").decode("utf-8")
        once = self.f.decrypt(ct.encode("utf-8")).decode("utf-8")
        assert once == "hello"
        assert not once.startswith(_FERNET_PREFIX)

    def test_double_decrypts_to_inner_ciphertext(self):
        # Double layer: encrypt(encrypt(plaintext)) → decrypt-once →
        # another Fernet token. This is the signal the unwrap helper
        # keys on.
        inner = self.f.encrypt(b"hello").decode("utf-8")
        outer = self.f.encrypt(inner.encode("utf-8")).decode("utf-8")
        once = self.f.decrypt(outer.encode("utf-8")).decode("utf-8")
        assert once.startswith(_FERNET_PREFIX)
        # And `once` itself decrypts under the same key → confirms the
        # _is_decryptable second check used by the unwrap helper.
        assert _is_decryptable(self.f, once) is True


class TestFernetPrefix:
    """`gAAAAA` is the base64-url framing of the Fernet version byte
    0x80 plus three zero bytes from the timestamp. Every Fernet token
    starts with this prefix. The backfill uses it to distinguish
    wrong-keyed ciphertext (skip) from legacy plaintext (re-encrypt)."""

    def test_constant_value(self):
        assert _FERNET_PREFIX == "gAAAAA"

    def test_real_token_matches_prefix(self):
        # Generate a fresh Fernet token and confirm the prefix sniff
        # is the right one.
        ct = Fernet(Fernet.generate_key()).encrypt(b"x").decode("utf-8")
        assert ct.startswith(_FERNET_PREFIX)
