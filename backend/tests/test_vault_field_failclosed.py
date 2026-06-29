"""Vault-field fail-closed + legacy-plaintext backfill regressions.

GHSA-3r7j-7h5r-gxgx follow-up. The old `decrypt_field` silently
returned the raw value when decryption failed, which hid exactly the
class of bug the 3r7j advisory reported (an import-side write path
forgot to encrypt; the vault UI rendered the plaintext as if it had
roundtripped cleanly). The fix is two parts:

  1. ``decrypt_field`` now fails closed — returns ``None`` + logs a
     warning on ``InvalidToken`` instead of returning the raw value.
  2. A one-shot startup backfill (``backfill_legacy_vault_fields``)
     re-encrypts any pre-existing plaintext rows so the fail-closed
     flip doesn't blank out legitimately-stored legacy values.

These tests pin both halves and the safety rail in the backfill:
wrong-keyed Fernet tokens (`gAAAAA…` prefix that fails decrypt) are
SKIPPED, not wrapped. Wrapping would lose recoverability — better to
let the operator see the broken row and investigate.

The backfill helper is tested at the row-level (`_backfill_row_fields`)
rather than the full DB walk because we don't need to spin up
PostgreSQL to exercise the cryptographic / fail-mode contract — that's
what `_table_specs` covers as a list-of-(model, columns) declaration
and what is tested separately.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet, InvalidToken

# Make sure a key is available before importing vault_crypto.
import os
os.environ.setdefault("VAULT_ENCRYPTION_KEY", Fernet.generate_key().decode())

from utils import vault_crypto
from utils.vault_crypto import decrypt_field, encrypt_field
from utils.vault_field_migration import (
    _backfill_row_fields,
    _FERNET_PREFIX,
    _table_specs,
)


# ── decrypt_field: fail-closed contract ──────────────────────────────


class TestDecryptFieldFailClosed:
    """The whole point of the change. Old behaviour was to round-trip
    the raw value on InvalidToken so the vault UI silently confirmed
    bad state. New behaviour: return None + log."""

    def test_roundtrip_still_works(self):
        ct = encrypt_field("secret-password")
        assert decrypt_field(ct) == "secret-password"

    def test_none_passes_through(self):
        # `None` always passes — same as the old behaviour. The fail-
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
        # wrong. Pin its presence + level so a future refactor can't
        # silently drop the only telemetry for this failure mode.
        with caplog.at_level(logging.WARNING, logger="utils.vault_crypto"):
            decrypt_field("garbage")
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert any("InvalidToken" in r.message for r in warnings)


# ── backfill: per-row contract ───────────────────────────────────────


def _row(**fields):
    """Lightweight stand-in for an ORM row — only `id` + the columns
    we're operating on are needed for the helper."""
    base = {"id": "row-1", "username": None, "password": None, "note": None}
    base.update(fields)
    return SimpleNamespace(**base)


def _fresh_stats():
    return {
        "rows_checked": 0,
        "fields_already_encrypted": 0,
        "fields_re_encrypted": 0,
        "skipped": 0,
    }


class TestBackfillRowFields:
    """Pin every branch of the per-row helper — already-encrypted vs
    legacy-plaintext vs wrong-keyed-Fernet vs None/empty."""

    def setup_method(self):
        # Real Fernet key so encrypt → decrypt actually exercises the
        # cryptographic boundary, not a mock.
        self.f = vault_crypto._get_fernet()

    def test_already_encrypted_left_alone(self):
        ct = encrypt_field("hello")
        row = _row(password=ct)
        stats = _fresh_stats()
        changed = _backfill_row_fields(row, ("password",), self.f, stats)
        assert changed is False
        assert row.password == ct  # untouched
        assert stats["fields_already_encrypted"] == 1
        assert stats["fields_re_encrypted"] == 0

    def test_legacy_plaintext_gets_encrypted(self):
        row = _row(password="legacy-cleartext")
        stats = _fresh_stats()
        changed = _backfill_row_fields(row, ("password",), self.f, stats)
        assert changed is True
        # New value decrypts back to the original plaintext.
        assert self.f.decrypt(row.password.encode("utf-8")).decode("utf-8") == "legacy-cleartext"
        assert stats["fields_re_encrypted"] == 1
        assert stats["skipped"] == 0

    def test_wrong_keyed_fernet_skipped_not_wrapped(self):
        # CRITICAL: a value that looks like Fernet (gAAAAA prefix) but
        # doesn't decrypt MUST be left alone. Wrapping ciphertext-as-
        # plaintext would produce nested ciphertext we can never
        # recover even if the original key turns up again.
        foreign = Fernet(Fernet.generate_key())
        ct = foreign.encrypt(b"sensitive").decode("utf-8")
        assert ct.startswith(_FERNET_PREFIX)  # sanity check
        row = _row(password=ct)
        stats = _fresh_stats()
        changed = _backfill_row_fields(row, ("password",), self.f, stats)
        assert changed is False
        assert row.password == ct  # PRESERVED — not double-wrapped
        assert stats["skipped"] == 1
        assert stats["fields_re_encrypted"] == 0

    def test_none_skipped_no_count(self):
        row = _row(password=None)
        stats = _fresh_stats()
        changed = _backfill_row_fields(row, ("password",), self.f, stats)
        assert changed is False
        assert stats == _fresh_stats()  # no counters bumped

    def test_empty_string_skipped_no_count(self):
        row = _row(password="")
        stats = _fresh_stats()
        changed = _backfill_row_fields(row, ("password",), self.f, stats)
        assert changed is False
        assert stats == _fresh_stats()

    def test_walks_multiple_columns(self):
        row = _row(
            username="plain-user",
            password=encrypt_field("already-ct"),
            note=None,
        )
        stats = _fresh_stats()
        changed = _backfill_row_fields(
            row, ("username", "password", "note"), self.f, stats
        )
        assert changed is True
        assert stats["fields_re_encrypted"] == 1   # username
        assert stats["fields_already_encrypted"] == 1  # password
        # note (None) doesn't count

    def test_non_str_value_logs_and_skips(self, caplog):
        # Defensive guard — every encrypted column is Text in the model,
        # but if a future schema change introduces a non-str type the
        # helper has to be loud, not silently mutate.
        row = _row(password=12345)  # type: ignore[arg-type]
        stats = _fresh_stats()
        with caplog.at_level(logging.WARNING, logger="utils.vault_field_migration"):
            changed = _backfill_row_fields(row, ("password",), self.f, stats)
        assert changed is False
        assert row.password == 12345
        assert stats["skipped"] == 1
        assert any("non-str" in r.message for r in caplog.records)

    def test_wrong_keyed_logs_warning(self, caplog):
        # Operator signal for "I rotated keys and forgot something" or
        # "I restored a backup with a stale key". Pin the log so future
        # refactors can't drop the telemetry.
        foreign = Fernet(Fernet.generate_key())
        row = _row(password=foreign.encrypt(b"x").decode("utf-8"))
        stats = _fresh_stats()
        with caplog.at_level(logging.WARNING, logger="utils.vault_field_migration"):
            _backfill_row_fields(row, ("password",), self.f, stats)
        msgs = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("SKIPPING" in m and "Fernet" in m for m in msgs)


# ── _table_specs sanity ──────────────────────────────────────────────


class TestTableSpecs:
    """`_table_specs` is the registry of every (model, columns) pair
    the backfill walks. If a new vault-encrypted table ever gets added
    elsewhere in the codebase, the corresponding entry must land here
    or the backfill will miss it — pin the current set so the failure
    mode is a noisy test failure, not a silent gap."""

    def test_expected_tables_present(self):
        specs = _table_specs()
        names = {m.__name__: cols for m, cols in specs}
        assert names == {
            "VaultItem": ("username", "password", "note"),
            "InfraVaultItem": ("username", "password", "note"),
            "SprayCampaign": ("password_used",),
            "SprayResult": ("username", "password"),
        }
