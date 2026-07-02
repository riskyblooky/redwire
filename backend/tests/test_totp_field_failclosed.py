"""TOTP-secret fail-closed + legacy-plaintext backfill regressions.

GHSA-rp23-74j3-mqmq (TOTP half). ``decrypt_totp_secret`` now fails
closed — returns ``None`` and logs a warning on ``InvalidToken``
(the branch that catches both legacy plaintext and wrong-key
ciphertext) instead of round-tripping the raw value. The backfill
helper in ``totp_field_migration`` makes that flip safe on upgrade
by re-encrypting any legacy plaintext ``users.totp_secret`` value
in place via raw SQL.

These tests pin the pure-Python pieces load-bearing for correctness
— the cryptographic boundary of ``decrypt_totp_secret`` and the
detection helper the backfill hinges on. The end-to-end table walk
is exercised by the boot-time smoke documented in the commit
message.
"""

from __future__ import annotations

import logging
import os

import pytest
from cryptography.fernet import Fernet

# Make sure a TOTP key is available before importing crypto.
os.environ.setdefault("TOTP_ENCRYPTION_KEY", Fernet.generate_key().decode())

from auth.crypto import decrypt_totp_secret, encrypt_totp_secret, _get_fernet
from utils.totp_field_migration import _FERNET_PREFIX, _is_decryptable


# ── decrypt_totp_secret: fail-closed contract ────────────────────────


class TestDecryptTotpFailClosed:
    """Pre-flip: any value that failed to decrypt was returned raw,
    so legacy plaintext base32 seeds continued to work end-to-end and
    the at-rest encryption guarantee silently didn't apply.
    Post-flip: everything except a valid ciphertext under the current
    key returns ``None``."""

    def test_roundtrip_still_works(self):
        ct = encrypt_totp_secret("JBSWY3DPEHPK3PXP")
        assert decrypt_totp_secret(ct) == "JBSWY3DPEHPK3PXP"

    def test_none_passes_through(self):
        # None indicates "user hasn't enrolled 2FA yet" — pass through so
        # the None check at the caller (2fa verify) still works.
        assert decrypt_totp_secret(None) is None

    def test_empty_string_passes_through(self):
        # Same shape as None — an unset field. The fail-closed flip
        # only affects populated-but-not-decryptable values.
        assert decrypt_totp_secret("") == ""

    def test_legacy_plaintext_returns_none(self):
        # Pre-flip this returned the raw base32 string, letting a
        # legacy user's 2FA continue working (and defeating the at-
        # rest guarantee). Post-flip: None, forcing re-enrollment.
        assert decrypt_totp_secret("JBSWY3DPEHPK3PXP") is None

    def test_garbage_returns_none(self):
        assert decrypt_totp_secret("not a token") is None

    def test_wrong_key_ciphertext_returns_none(self):
        # A Fernet-shaped value encrypted under a foreign key must
        # not silently succeed as plaintext (that was the pre-flip
        # bug). Post-flip: None.
        foreign = Fernet(Fernet.generate_key())
        ct = foreign.encrypt(b"JBSWY3DPEHPK3PXP").decode("utf-8")
        assert decrypt_totp_secret(ct) is None

    def test_invalid_token_emits_warning(self, caplog):
        # Pin the log signal: this is the only telemetry the operator
        # gets for a legacy row that slipped past the backfill.
        with caplog.at_level(logging.WARNING, logger="auth.crypto"):
            decrypt_totp_secret("garbage")
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert any("InvalidToken" in r.message for r in warnings)


# ── _is_decryptable: the backfill's decision boundary ────────────────


class TestIsDecryptable:
    """The predicate that decides whether a row is legacy plaintext
    (re-encrypt), already-encrypted (leave), or wrong-keyed-Fernet
    (skip). Every branch of the backfill routes through this."""

    def setup_method(self):
        self.f = _get_fernet()

    def test_valid_ciphertext_true(self):
        ct = encrypt_totp_secret("JBSWY3DPEHPK3PXP")
        assert _is_decryptable(self.f, ct) is True

    def test_legacy_plaintext_false(self):
        # The case the backfill exists to detect. Base32 TOTP seeds
        # are what pre-migration users have.
        assert _is_decryptable(self.f, "JBSWY3DPEHPK3PXP") is False

    def test_wrong_keyed_ciphertext_false(self):
        # `gAAAAA` prefix but not decryptable under our key — must
        # read as "not decryptable" so the wrong-keyed branch in the
        # backfill engages (skip, not wrap).
        foreign = Fernet(Fernet.generate_key())
        ct = foreign.encrypt(b"seed").decode("utf-8")
        assert _is_decryptable(self.f, ct) is False


# ── _FERNET_PREFIX: framing constant ─────────────────────────────────


class TestFernetPrefix:
    """The framing sniff the backfill uses to distinguish wrong-keyed
    ciphertext (skip, don't re-wrap) from legacy plaintext (safe to
    re-encrypt in place). Fernet tokens are base64-url of version
    byte 0x80 plus three zero bytes of timestamp framing."""

    def test_constant_value(self):
        assert _FERNET_PREFIX == "gAAAAA"

    def test_real_token_matches_prefix(self):
        ct = Fernet(Fernet.generate_key()).encrypt(b"seed").decode("utf-8")
        assert ct.startswith(_FERNET_PREFIX)

    def test_typical_base32_seed_does_not_match_prefix(self):
        # A legit-shaped TOTP base32 seed does not accidentally
        # collide with the Fernet prefix — this is why the "not
        # startswith gAAAAA" branch reliably identifies plaintext.
        assert not "JBSWY3DPEHPK3PXP".startswith(_FERNET_PREFIX)
