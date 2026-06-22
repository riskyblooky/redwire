"""Regression tests for the vault file at-rest encryption backfill.

GHSA-3r7j-7h5r-gxgx Issue 3 follow-up. The pure logic — Fernet shape
detection — is the load-bearing piece: a false positive would skip a
legitimate plaintext blob (leaving it unencrypted but flagged "done"),
and a false negative would just trigger an idempotent re-encrypt
round-trip (no security impact, only wasted I/O). The DB+MinIO
integration is exercised by the live smoke documented in the commit
message; this file pins the shape-detection contract.
"""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from utils.vault_migration import _is_already_fernet


class TestFernetShapeDetection:
    """``_is_already_fernet`` decides whether to skip the
    encrypt-and-re-upload round-trip during the legacy backfill.

    The function is intentionally a cheap prefix sniff (the literal
    bytes ``gAAAAA``, which is the url-safe base64 prefix of every
    Fernet token's version byte 0x80). Real Fernet validation would
    work too but costs orders of magnitude more per row; with
    thousands of legacy blobs the prefix check is the right call.
    """

    def test_real_fernet_token_detected(self):
        """Round-trip: encrypt a payload, verify the result is
        classified as Fernet-shaped. This is the must-not-break
        invariant — if the prefix sniff ever stops recognising real
        Fernet output, the backfill will re-encrypt every row on
        every boot (correctness preserved, wasted I/O huge)."""
        fernet = Fernet(Fernet.generate_key())
        ciphertext = fernet.encrypt(b"hello world")
        assert _is_already_fernet(ciphertext)

    def test_multiple_real_fernet_tokens_all_detected(self):
        """Fernet uses random IVs — different keys + different
        plaintexts must all still produce the same recognised prefix."""
        for _ in range(10):
            f = Fernet(Fernet.generate_key())
            ct = f.encrypt(b"payload-" + Fernet.generate_key())
            assert _is_already_fernet(ct), f"missed Fernet token: {ct[:20]!r}"

    @pytest.mark.parametrize("plaintext", [
        b"%PDF-1.4 leading legacy header",
        b"-----BEGIN OPENSSH PRIVATE KEY-----",
        b"apiVersion: v1\nkind: Config\n",
        b"\x89PNG\r\n\x1a\n",          # PNG magic
        b"PK\x03\x04",                 # ZIP magic
        b"",                           # empty
    ])
    def test_legacy_plaintext_not_detected(self, plaintext):
        """Common plaintext file shapes (vault uploads are SSH keys,
        kubeconfigs, PDFs, certs) must NOT be classified as Fernet —
        otherwise the backfill would mark them encrypted-already and
        leave the plaintext blob in MinIO."""
        assert not _is_already_fernet(plaintext)

    def test_just_the_prefix_alone_is_too_short_to_be_a_real_token(self):
        """An attacker-controlled file that consists ONLY of ``gAAAAA``
        would falsely test as Fernet. That's a 6-byte file — orders of
        magnitude smaller than any real Fernet token (overhead alone
        is ~80 bytes). The misclassification is benign: the backfill
        would skip re-encryption, leaving the file as-is and flipping
        the flag to 1. On next download the fail-soft decrypt_bytes
        would pass the raw bytes through. So a real attacker doesn't
        gain anything from this; pinning the behaviour for clarity."""
        assert _is_already_fernet(b"gAAAAA")

    def test_non_bytes_rejected(self):
        """Defensive — the helper is called with whatever
        ``storage_service.download_file`` returned. If something ever
        returns a str (it shouldn't), don't crash; just say "not
        Fernet" and let the encrypt-path handle it."""
        assert not _is_already_fernet("gAAAAA_string_not_bytes")
        assert not _is_already_fernet(None)
        assert not _is_already_fernet(123)

    def test_partial_prefix_match_rejected(self):
        """``gAAA`` alone (4 chars) shouldn't match; we require the
        full 6-char prefix because shorter prefixes occur naturally
        in random data."""
        assert not _is_already_fernet(b"gAAA")
        assert not _is_already_fernet(b"gAAAA")
