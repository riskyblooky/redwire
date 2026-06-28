"""Engagement-export/import optional AES passphrase regressions.

GHSA-3r7j-7h5r-gxgx follow-up. Engagement exports carry plaintext
vault credentials by design (the destination instance re-encrypts under
its own key on import), so an admin who needs to hand off the archive
over an untrusted channel can now wrap it in pyzipper's AES-256
extension. Round-trip support requires both endpoints (export + import)
to speak the passphrase, and the import endpoint must reject encrypted
archives that arrive without a passphrase or with the wrong one — this
test module pins that contract.

Tests live at the helper layer (`_validate_passphrase`,
`_zip_is_aes_encrypted`, `_open_engagement_archive`) because the
endpoints themselves require a populated DB + auth; the helpers ARE
the cryptographic boundary the endpoints delegate to, so pinning them
covers the security-relevant surface.
"""

from __future__ import annotations

import io
import json
import zipfile

import pyzipper
import pytest
from fastapi import HTTPException

from routers.engagements_transfer import (
    MIN_EXPORT_PASSPHRASE_LEN,
    _open_engagement_archive,
    _validate_passphrase,
    _zip_is_aes_encrypted,
)


# ── builders ──────────────────────────────────────────────────────────


def _build_plain_zip() -> bytes:
    """Build a minimal valid engagement archive (no encryption)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"source": "redwire", "version": "1.1"}))
        zf.writestr("engagement.json", json.dumps({"engagement": {"name": "x"}, "users": {}}))
    return buf.getvalue()


def _build_encrypted_zip(passphrase: str) -> bytes:
    """Build the same minimal archive, but pyzipper-AES wrapped."""
    buf = io.BytesIO()
    with pyzipper.AESZipFile(
        buf, "w", compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES
    ) as zf:
        zf.setpassword(passphrase.encode("utf-8"))
        zf.writestr("manifest.json", json.dumps({"source": "redwire", "version": "1.1"}))
        zf.writestr("engagement.json", json.dumps({"engagement": {"name": "x"}, "users": {}}))
    return buf.getvalue()


# ── _validate_passphrase ─────────────────────────────────────────────


class TestValidatePassphrase:
    """Length is the only constraint; we don't normalise or enforce
    complexity (operator-supplied phrases are assumed strong)."""

    def test_none_passes(self):
        # No passphrase = plain archive, valid case.
        assert _validate_passphrase(None, kind="export") is None

    def test_empty_string_passes(self):
        # Empty header value also treated as absent — frontend may send
        # an empty string when the user clears the field, don't 400 that.
        assert _validate_passphrase("", kind="export") is None

    def test_too_short_rejected(self):
        with pytest.raises(HTTPException) as exc:
            _validate_passphrase("a" * (MIN_EXPORT_PASSPHRASE_LEN - 1), kind="export")
        assert exc.value.status_code == 400
        assert "at least" in exc.value.detail
        assert str(MIN_EXPORT_PASSPHRASE_LEN) in exc.value.detail

    def test_min_length_accepted(self):
        out = _validate_passphrase("a" * MIN_EXPORT_PASSPHRASE_LEN, kind="export")
        assert out == "a" * MIN_EXPORT_PASSPHRASE_LEN

    def test_value_returned_verbatim(self):
        # No NFKC / trim / case-fold — pyzipper hashes the bytes exactly,
        # so any normalisation would silently change the key.
        pw = "  Mixed Case With   Spaces  " + "x" * 8
        assert _validate_passphrase(pw, kind="import") == pw

    def test_kind_label_in_error(self):
        # Different verb shows up in error so the UI can render it
        # without further interpolation.
        for kind in ("export", "import"):
            with pytest.raises(HTTPException) as exc:
                _validate_passphrase("short", kind=kind)
            assert kind.capitalize() in exc.value.detail


# ── _zip_is_aes_encrypted ────────────────────────────────────────────


class TestZipIsAesEncrypted:
    def test_plain_zip_false(self):
        zf = zipfile.ZipFile(io.BytesIO(_build_plain_zip()))
        assert _zip_is_aes_encrypted(zf) is False

    def test_aes_zip_true_via_stdlib_reader(self):
        # IMPORTANT: even when opened with stdlib zipfile (no decryption
        # capability), the central-directory flag bits are still readable
        # — that's the whole point of the sniff: we use the cheap stdlib
        # parser to detect encryption before deciding whether to pull
        # in pyzipper.
        bytes_ = _build_encrypted_zip("a" * MIN_EXPORT_PASSPHRASE_LEN)
        zf = zipfile.ZipFile(io.BytesIO(bytes_))
        assert _zip_is_aes_encrypted(zf) is True


# ── _open_engagement_archive ─────────────────────────────────────────


class TestOpenEngagementArchive:
    """The thin layer the import endpoints call to get a read-ready
    zipfile object regardless of encryption. The endpoints stay
    agnostic — they just call ``zf.read(name)`` afterwards."""

    PASSPHRASE = "correct-horse-battery-staple-extra"

    def test_plain_archive_opens(self):
        zf = _open_engagement_archive(_build_plain_zip(), passphrase=None)
        assert "manifest.json" in zf.namelist()

    def test_plain_archive_ignores_supplied_passphrase(self):
        # An operator who clicks "encrypted" and supplies a passphrase
        # but uploads a plain ZIP should still succeed — the passphrase
        # is silently ignored when no encryption is present. Avoids a
        # confusing error when the file naming was misleading.
        zf = _open_engagement_archive(_build_plain_zip(), passphrase=self.PASSPHRASE)
        assert "manifest.json" in zf.namelist()

    def test_encrypted_archive_with_correct_passphrase(self):
        zf = _open_engagement_archive(
            _build_encrypted_zip(self.PASSPHRASE), passphrase=self.PASSPHRASE
        )
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["source"] == "redwire"

    def test_encrypted_archive_without_passphrase_400(self):
        with pytest.raises(HTTPException) as exc:
            _open_engagement_archive(
                _build_encrypted_zip(self.PASSPHRASE), passphrase=None
            )
        assert exc.value.status_code == 400
        # Error has to be unambiguous about WHY it failed — operator
        # might not know the file is encrypted until they try.
        assert "encrypted" in exc.value.detail.lower()
        assert "passphrase" in exc.value.detail.lower()

    def test_encrypted_archive_with_wrong_passphrase_400(self):
        with pytest.raises(HTTPException) as exc:
            _open_engagement_archive(
                _build_encrypted_zip(self.PASSPHRASE), passphrase="wrong-passphrase-12345"
            )
        assert exc.value.status_code == 400
        # Distinct from the no-passphrase case so the UI can render
        # differently (operator who supplied a key got it wrong, vs
        # operator who didn't know one was needed).
        assert "decrypt" in exc.value.detail.lower()
        assert "passphrase" in exc.value.detail.lower()

    def test_malformed_zip_400(self):
        with pytest.raises(HTTPException) as exc:
            _open_engagement_archive(b"not a zip at all", passphrase=None)
        assert exc.value.status_code == 400
        assert "Invalid ZIP" in exc.value.detail

    def test_can_read_every_entry_post_unlock(self):
        """Probe-read in the helper only touches the first non-empty
        entry; subsequent reads in the caller must also succeed. Pin
        that there's no probe-only short-circuit hiding a partial unlock."""
        bytes_ = _build_encrypted_zip(self.PASSPHRASE)
        zf = _open_engagement_archive(bytes_, passphrase=self.PASSPHRASE)
        # Both entries readable, returns the same JSON we wrote.
        assert json.loads(zf.read("manifest.json"))["source"] == "redwire"
        assert json.loads(zf.read("engagement.json"))["engagement"]["name"] == "x"


# ── round-trip via the helpers ───────────────────────────────────────


class TestRoundTripContract:
    """The end-to-end shape an admin would actually exercise: build
    an AES-encrypted archive on the export side, hand it off, then
    open it on the import side with the same passphrase."""

    def test_round_trip_preserves_content(self):
        pw = "round-trip-passphrase-1234"
        # Simulate the export-side build (verbatim of what
        # export_engagement does inside the `if passphrase` branch).
        zip_buf = io.BytesIO()
        with pyzipper.AESZipFile(
            zip_buf, "w", compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES
        ) as zf:
            zf.setpassword(pw.encode("utf-8"))
            zf.writestr("manifest.json", json.dumps({"source": "redwire", "version": "1.1"}))
            payload = {"engagement": {"name": "client-x"}, "findings": [], "users": {}}
            zf.writestr("engagement.json", json.dumps(payload))

        # Import side. The bytes go through the same helper the import
        # endpoint uses.
        zf2 = _open_engagement_archive(zip_buf.getvalue(), passphrase=pw)
        data = json.loads(zf2.read("engagement.json"))
        assert data["engagement"]["name"] == "client-x"
