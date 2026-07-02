"""Engagement archive content-hash manifest regressions.

GHSA-vwgf-r8qp-8gwr (CWE-353). Every v1.2+ export carries a SHA-256
per archive member plus a root digest over the sorted digest map. On
import the digest map is recomputed member-by-member; any mismatch is
a 400 refusal before ORM ingestion, catching tampering-in-transit and
storage corruption. Legacy pre-1.2 archives (no ``digests`` field) are
refused by default and only accepted when the operator opts into
legacy behaviour via ``ENGAGEMENT_IMPORT_REQUIRE_DIGEST=false``.

These tests pin the pure-Python pieces (the digest helpers and the
verification gate) — the actual endpoints require a populated DB and
auth, but the verification gate IS what the endpoints delegate to, so
pinning it covers the CWE-353 boundary.
"""

from __future__ import annotations

import io
import json
import zipfile

import pytest
from fastapi import HTTPException

from routers.engagements_transfer import (
    IMPORT_REQUIRE_DIGEST,
    MANIFEST_VERSION,
    _compute_root_digest,
    _sha256_hex,
    _verify_archive_digests,
)


# ── builders ──────────────────────────────────────────────────────────


def _build_archive(members: dict[str, bytes], manifest_extra: dict | None = None) -> zipfile.ZipFile:
    """Build a valid v1.2 archive: compute per-member digests + root,
    write manifest.json first, then all named members. Returns an open
    ZipFile handle positioned at member 0.
    """
    digests = {name: _sha256_hex(members[name]) for name in sorted(members)}
    root_digest = _compute_root_digest(digests)
    manifest = {
        "version": MANIFEST_VERSION,
        "source": "redwire",
        "engagement_name": "test",
        "digests": digests,
        "root_digest": root_digest,
    }
    if manifest_extra:
        manifest.update(manifest_extra)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
        for name in sorted(members):
            zf.writestr(name, members[name])
    buf.seek(0)
    return zipfile.ZipFile(buf, "r")


def _tamper_member(zf_bytes: bytes, name: str, replacement: bytes) -> bytes:
    """Rebuild a ZIP with ``name`` replaced by ``replacement`` bytes.
    Every other member (including manifest.json) is copied verbatim,
    so the manifest's digest for ``name`` no longer matches.
    """
    src = zipfile.ZipFile(io.BytesIO(zf_bytes), "r")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            data = replacement if info.filename == name else src.read(info.filename)
            dst.writestr(info.filename, data)
    return out.getvalue()


# ── _sha256_hex / _compute_root_digest ───────────────────────────────


class TestSha256Hex:
    def test_known_vector(self):
        # RFC-published SHA-256 test vector — the empty-input digest.
        assert _sha256_hex(b"") == (
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        )

    def test_stable_across_calls(self):
        # Sanity — same input, same output. Guards against a future
        # refactor that accidentally salts the hash.
        payload = b"engagement.json contents"
        assert _sha256_hex(payload) == _sha256_hex(payload)


class TestComputeRootDigest:
    def test_order_independent(self):
        # Two identical digest maps in different insertion order MUST
        # produce the same root — the on-disk manifest is deterministic
        # regardless of member-write order.
        a = _compute_root_digest({"z": "aaa", "a": "bbb"})
        b = _compute_root_digest({"a": "bbb", "z": "aaa"})
        assert a == b

    def test_value_sensitive(self):
        # A single character change in any digest value flips the root
        # — the root is a self-check over the map's contents.
        a = _compute_root_digest({"engagement.json": "a" * 64})
        b = _compute_root_digest({"engagement.json": "b" + "a" * 63})
        assert a != b

    def test_key_sensitive(self):
        # Same digests, different filename → different root. Renaming
        # a member without updating the map has to be caught.
        a = _compute_root_digest({"engagement.json": "d" * 64})
        b = _compute_root_digest({"other.json": "d" * 64})
        assert a != b


# ── _verify_archive_digests: happy path ──────────────────────────────


class TestVerifyHappyPath:
    def test_clean_archive_verifies(self):
        zf = _build_archive({"engagement.json": b'{"engagement":{"name":"x"}}'})
        manifest = json.loads(zf.read("manifest.json"))
        # Must not raise
        _verify_archive_digests(zf, manifest)

    def test_multiple_members_verify(self):
        zf = _build_archive({
            "engagement.json": b'{"engagement":{"name":"x"}}',
            "SECURITY_WARNING.txt": b"secrets ahead",
            "attachments/e/1/screenshot.png": b"\x89PNG\r\n\x1a\n" + b"x" * 100,
        })
        manifest = json.loads(zf.read("manifest.json"))
        _verify_archive_digests(zf, manifest)


# ── _verify_archive_digests: rejects tampering ───────────────────────


class TestVerifyRejectsTampering:
    def _tampered_archive(self, target: str, replacement: bytes) -> tuple[zipfile.ZipFile, dict]:
        members = {
            "engagement.json": b'{"engagement":{"name":"x"}}',
            "attachments/e/1/note.txt": b"original evidence",
        }
        good = _build_archive(members)
        good_bytes = good.fp.getvalue() if hasattr(good.fp, "getvalue") else b""
        # Rebuild from the raw source bytes so we control the tamper.
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", good.read("manifest.json"))
            for name in sorted(members):
                zf.writestr(name, members[name])
        raw = buf.getvalue()
        tampered = _tamper_member(raw, target, replacement)
        zf = zipfile.ZipFile(io.BytesIO(tampered), "r")
        manifest = json.loads(zf.read("manifest.json"))
        return zf, manifest

    def test_tampered_engagement_json_rejected(self):
        zf, manifest = self._tampered_archive("engagement.json", b'{"engagement":{"name":"pwned"}}')
        with pytest.raises(HTTPException) as exc:
            _verify_archive_digests(zf, manifest)
        assert exc.value.status_code == 400
        assert "integrity" in exc.value.detail.lower()

    def test_tampered_attachment_rejected(self):
        zf, manifest = self._tampered_archive("attachments/e/1/note.txt", b"forged evidence")
        with pytest.raises(HTTPException) as exc:
            _verify_archive_digests(zf, manifest)
        assert exc.value.status_code == 400

    def test_missing_declared_member_rejected(self):
        # Build an archive but drop a member listed in the manifest —
        # the digest verification must complain about the absence, not
        # ignore it.
        members = {
            "engagement.json": b'{"engagement":{"name":"x"}}',
            "attachments/gone.txt": b"was here",
        }
        digests = {name: _sha256_hex(members[name]) for name in sorted(members)}
        root_digest = _compute_root_digest(digests)
        manifest = {
            "version": MANIFEST_VERSION,
            "source": "redwire",
            "digests": digests,
            "root_digest": root_digest,
        }
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps(manifest))
            zf.writestr("engagement.json", members["engagement.json"])
            # Deliberately don't write attachments/gone.txt
        zf = zipfile.ZipFile(io.BytesIO(buf.getvalue()), "r")
        with pytest.raises(HTTPException) as exc:
            _verify_archive_digests(zf, manifest)
        assert exc.value.status_code == 400
        assert "missing" in exc.value.detail.lower()

    def test_tampered_root_digest_rejected(self):
        # An attacker who recomputes the per-file digests to match
        # their tampered content must also have the correct root, or
        # the map-integrity self-check trips.
        members = {"engagement.json": b'{"engagement":{"name":"x"}}'}
        digests = {"engagement.json": _sha256_hex(members["engagement.json"])}
        manifest = {
            "version": MANIFEST_VERSION,
            "source": "redwire",
            "digests": digests,
            "root_digest": "0" * 64,  # wrong root
        }
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps(manifest))
            zf.writestr("engagement.json", members["engagement.json"])
        zf = zipfile.ZipFile(io.BytesIO(buf.getvalue()), "r")
        with pytest.raises(HTTPException) as exc:
            _verify_archive_digests(zf, manifest)
        assert exc.value.status_code == 400
        assert "root_digest" in exc.value.detail


# ── _verify_archive_digests: pre-1.2 legacy archives ─────────────────


class TestLegacyArchiveHandling:
    def test_no_digests_field_rejected_by_default(self):
        # The IMPORT_REQUIRE_DIGEST flag is loaded at module import
        # time from env, and this test suite runs with the default
        # (True). A manifest without ``digests`` must refuse.
        assert IMPORT_REQUIRE_DIGEST is True, (
            "Test sanity: this suite depends on the default "
            "ENGAGEMENT_IMPORT_REQUIRE_DIGEST=true"
        )
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps({
                "version": "1.1",  # legacy shape — no digests
                "source": "redwire",
            }))
            zf.writestr("engagement.json", b'{"engagement":{"name":"x"}}')
        zf = zipfile.ZipFile(io.BytesIO(buf.getvalue()), "r")
        manifest = {"version": "1.1", "source": "redwire"}
        with pytest.raises(HTTPException) as exc:
            _verify_archive_digests(zf, manifest)
        assert exc.value.status_code == 400
        assert "missing manifest.digests" in exc.value.detail.lower()

    def test_empty_digests_map_treated_as_legacy(self):
        # An empty ``digests: {}`` is a downgrade attempt: legit v1.2
        # exports always have at least engagement.json. Reject it.
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps({
                "version": "1.2",
                "source": "redwire",
                "digests": {},
                "root_digest": _compute_root_digest({}),
            }))
            zf.writestr("engagement.json", b'{"engagement":{"name":"x"}}')
        zf = zipfile.ZipFile(io.BytesIO(buf.getvalue()), "r")
        manifest = {"version": "1.2", "source": "redwire", "digests": {}}
        with pytest.raises(HTTPException) as exc:
            _verify_archive_digests(zf, manifest)
        assert exc.value.status_code == 400


# ── attacker downgrade attempt: v1.1 label but v1.2 content ──────────


class TestDowngradeAttack:
    def test_v11_label_with_no_digests_still_rejected(self):
        # An attacker who sets ``version: "1.1"`` but presents forged
        # content still has no digests to verify against — the check
        # runs on the presence of the map, not the version string.
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps({
                "version": "1.1",
                "source": "redwire",
            }))
            zf.writestr("engagement.json", b'{"engagement":{"name":"pwned"}}')
        zf = zipfile.ZipFile(io.BytesIO(buf.getvalue()), "r")
        manifest = {"version": "1.1", "source": "redwire"}
        with pytest.raises(HTTPException):
            _verify_archive_digests(zf, manifest)


# ── manifest.digests shape validation ────────────────────────────────


class TestDigestMapShapeValidation:
    """Belt-and-suspenders on the digest-map shape. The core CWE-353
    check is content-vs-expected; but a manifest with weird shapes
    (list values, uppercase hex, truncated digests) should reject
    outright rather than fall through to a confusing mismatch error."""

    def _archive_with(self, digest_value) -> tuple[zipfile.ZipFile, dict]:
        # Craft a manifest where engagement.json's digest slot has a
        # deliberately wrong shape. The actual member is present with
        # some bytes; verification should complain about the SHAPE of
        # the manifest entry, not do a hash compare.
        buf = io.BytesIO()
        manifest = {
            "version": "1.2",
            "source": "redwire",
            "digests": {"engagement.json": digest_value},
            "root_digest": "0" * 64,
        }
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest))
            zf.writestr("engagement.json", b"{}")
        zf = zipfile.ZipFile(io.BytesIO(buf.getvalue()), "r")
        return zf, manifest

    def test_non_string_digest_value_rejected(self):
        zf, manifest = self._archive_with(["not", "a", "string"])
        with pytest.raises(HTTPException) as exc:
            _verify_archive_digests(zf, manifest)
        assert exc.value.status_code == 400
        assert "not a valid" in exc.value.detail.lower()

    def test_uppercase_hex_rejected(self):
        # Fernet-style lower-hex canonical only. Uppercase would still
        # compare equal case-insensitively, but pinning the shape avoids
        # ambiguity across future consumers.
        zf, manifest = self._archive_with("ABCD" * 16)
        with pytest.raises(HTTPException) as exc:
            _verify_archive_digests(zf, manifest)
        assert exc.value.status_code == 400

    def test_wrong_length_rejected(self):
        # SHA-256 in hex is exactly 64 chars. Anything else is malformed.
        zf, manifest = self._archive_with("abcd" * 15)  # 60 chars
        with pytest.raises(HTTPException) as exc:
            _verify_archive_digests(zf, manifest)
        assert exc.value.status_code == 400

    def test_non_hex_char_rejected(self):
        zf, manifest = self._archive_with("z" + "a" * 63)
        with pytest.raises(HTTPException) as exc:
            _verify_archive_digests(zf, manifest)
        assert exc.value.status_code == 400


# ── MANIFEST_VERSION pin ─────────────────────────────────────────────


class TestManifestVersion:
    def test_current_version_is_1_2(self):
        # Pin the version so a future bump has to consciously update
        # this test — accidentally shipping a v1.3 export that pre-1.3
        # importers can't verify would repeat the CWE.
        assert MANIFEST_VERSION == "1.2"
