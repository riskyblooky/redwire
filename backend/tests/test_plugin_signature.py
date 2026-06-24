"""Regressions for the plugin Ed25519 signature gate.

GHSA-2rv7-jv5j-m4jg follow-up. Plugin code runs in-process with full
backend privileges; the signature gate is the trust anchor that lets
an operator separate "I trust this admin to upload" from "I trust
this plugin came from a known author". The pure logic — digest
canonicalisation, signature verify, mode-dispatch (off / preferred /
required) — must be deterministic across the cases that fail-close
the gate. These tests pin each branch.
"""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from utils import plugin_signature
from utils.plugin_signature import (
    VerifyMode,
    compute_manifest_digest,
    find_signature_file,
    gate_plugin_load,
    get_verify_mode,
    verify_plugin_signature,
)


# ── helpers ──────────────────────────────────────────────────────────


def _gen_keypair() -> tuple[Ed25519PrivateKey, str]:
    """Return (private_key, base64_public_key) — the test fixture
    operator pubkey form."""
    priv = Ed25519PrivateKey.generate()
    pub_bytes = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return priv, base64.b64encode(pub_bytes).decode("ascii")


def _build_plugin(tmp_path: Path, name: str = "demo") -> Path:
    """Create a minimal plugin directory layout matching what the
    loader expects: a yaml manifest + a Python module file."""
    p = tmp_path / name
    p.mkdir(parents=True)
    (p / "plugin.yaml").write_text(
        f"name: {name}\nversion: 1.0.0\nmin_redwire_version: 1.0.0\n"
    )
    (p / "__init__.py").write_text("def setup(**_): pass\n")
    (p / "helper.py").write_text("X = 1\n")
    return p


def _sign_plugin(plugin_dir: Path, priv: Ed25519PrivateKey) -> None:
    """Write a valid plugin.yaml.sig signing the current contents."""
    digest = compute_manifest_digest(plugin_dir)
    sig = priv.sign(digest)
    (plugin_dir / "plugin.yaml.sig").write_text(
        base64.b64encode(sig).decode("ascii") + "\n"
    )


# ── digest canonicalisation ─────────────────────────────────────────


def test_digest_is_stable_for_same_inputs(tmp_path):
    """Two plugin dirs with identical contents must hash identically.
    This is the property the verifier relies on: digest computed at
    sign time must equal digest computed at verify time."""
    p1 = _build_plugin(tmp_path / "a", "demo")
    p2 = _build_plugin(tmp_path / "b", "demo")
    assert compute_manifest_digest(p1) == compute_manifest_digest(p2)


def test_digest_changes_when_file_changes(tmp_path):
    """Tamper detection. If this fails, an attacker can swap a
    plugin's __init__.py and reuse the original signature."""
    p = _build_plugin(tmp_path, "demo")
    before = compute_manifest_digest(p)
    (p / "__init__.py").write_text("def setup(**_): pass\n# evil\n")
    after = compute_manifest_digest(p)
    assert before != after


def test_digest_changes_when_file_added(tmp_path):
    """A new file in the plugin directory MUST change the digest —
    otherwise an attacker could add a malicious sibling module that
    runs at import time and the signature would still verify."""
    p = _build_plugin(tmp_path, "demo")
    before = compute_manifest_digest(p)
    (p / "evil.py").write_text("import os; os.system('rm -rf /')\n")
    after = compute_manifest_digest(p)
    assert before != after


def test_digest_excludes_pycache(tmp_path):
    """``__pycache__`` is build output; including it would make the
    digest non-deterministic across Python versions / runs. The
    exclude must hold even for nested __pycache__ dirs."""
    p = _build_plugin(tmp_path, "demo")
    before = compute_manifest_digest(p)
    pycache = p / "__pycache__"
    pycache.mkdir()
    (pycache / "anything.pyc").write_bytes(b"\x00\x01\x02")
    (pycache / "nested" / "subdir").mkdir(parents=True)
    (pycache / "nested" / "subdir" / "deep.pyc").write_bytes(b"\xff")
    after = compute_manifest_digest(p)
    assert before == after


def test_digest_excludes_signature_file(tmp_path):
    """The signature file itself cannot participate in the digest —
    that would be self-referential."""
    p = _build_plugin(tmp_path, "demo")
    before = compute_manifest_digest(p)
    (p / "plugin.yaml.sig").write_text("abc\n")
    after = compute_manifest_digest(p)
    assert before == after


# ── verify_plugin_signature ─────────────────────────────────────────


def test_verify_succeeds_on_signed_plugin(tmp_path, monkeypatch):
    priv, pub_b64 = _gen_keypair()
    p = _build_plugin(tmp_path, "demo")
    _sign_plugin(p, priv)
    monkeypatch.setenv("PLUGIN_VERIFY_PUBKEY", pub_b64)

    ok, reason = verify_plugin_signature(p)
    assert ok is True
    assert "verified" in reason


def test_verify_fails_when_pubkey_missing(tmp_path, monkeypatch):
    priv, _ = _gen_keypair()
    p = _build_plugin(tmp_path, "demo")
    _sign_plugin(p, priv)
    monkeypatch.delenv("PLUGIN_VERIFY_PUBKEY", raising=False)

    ok, reason = verify_plugin_signature(p)
    assert ok is False
    assert "PLUGIN_VERIFY_PUBKEY" in reason


def test_verify_fails_when_no_signature_file(tmp_path, monkeypatch):
    _, pub_b64 = _gen_keypair()
    p = _build_plugin(tmp_path, "demo")
    monkeypatch.setenv("PLUGIN_VERIFY_PUBKEY", pub_b64)

    ok, reason = verify_plugin_signature(p)
    assert ok is False
    assert "no signature file" in reason


def test_verify_fails_on_tamper(tmp_path, monkeypatch):
    """The exact attack the gate is designed to catch — sign a known-
    good plugin then mutate one byte and confirm the signature
    refuses."""
    priv, pub_b64 = _gen_keypair()
    p = _build_plugin(tmp_path, "demo")
    _sign_plugin(p, priv)
    monkeypatch.setenv("PLUGIN_VERIFY_PUBKEY", pub_b64)

    # Verify pre-tamper is good (sanity).
    ok, _ = verify_plugin_signature(p)
    assert ok is True

    # Now tamper.
    (p / "helper.py").write_text("X = 2\n")
    ok, reason = verify_plugin_signature(p)
    assert ok is False
    assert "does not match" in reason


def test_verify_fails_with_wrong_pubkey(tmp_path, monkeypatch):
    """A plugin signed with key A must NOT verify under operator
    pubkey B. This is the keychain-separation contract."""
    priv_a, _ = _gen_keypair()
    _, pub_b = _gen_keypair()
    p = _build_plugin(tmp_path, "demo")
    _sign_plugin(p, priv_a)
    monkeypatch.setenv("PLUGIN_VERIFY_PUBKEY", pub_b)

    ok, reason = verify_plugin_signature(p)
    assert ok is False
    assert "does not match" in reason


def test_verify_fails_on_bad_pubkey_format(tmp_path, monkeypatch):
    p = _build_plugin(tmp_path, "demo")
    monkeypatch.setenv("PLUGIN_VERIFY_PUBKEY", "not-valid-base64!!!")
    ok, reason = verify_plugin_signature(p)
    assert ok is False
    assert "base64" in reason


def test_verify_fails_on_wrong_length_signature(tmp_path, monkeypatch):
    """Ed25519 sigs are exactly 64 bytes — a longer/shorter blob is
    not a legitimate signature, fail before invoking the crypto
    library."""
    _, pub_b64 = _gen_keypair()
    p = _build_plugin(tmp_path, "demo")
    (p / "plugin.yaml.sig").write_text(base64.b64encode(b"too short").decode())
    monkeypatch.setenv("PLUGIN_VERIFY_PUBKEY", pub_b64)

    ok, reason = verify_plugin_signature(p)
    assert ok is False
    assert "Ed25519 is 64" in reason


# ── gate_plugin_load mode dispatch ──────────────────────────────────


def test_gate_off_loads_everything(tmp_path, monkeypatch):
    """Default mode preserves current behaviour. Unsigned plugins
    load, signed ones load, tampered ones load — no gate."""
    p = _build_plugin(tmp_path, "demo")
    monkeypatch.setenv("PLUGIN_VERIFY", "off")
    load, reason = gate_plugin_load(p, "demo")
    assert load is True
    assert reason is None


def test_gate_preferred_soft_passes_unsigned(tmp_path, monkeypatch):
    """``preferred`` mode loads a plugin with no signature (logs a
    warning) so deployments can roll out the env var without breaking
    existing in-tree plugins."""
    _, pub_b64 = _gen_keypair()
    p = _build_plugin(tmp_path, "demo")
    monkeypatch.setenv("PLUGIN_VERIFY", "preferred")
    monkeypatch.setenv("PLUGIN_VERIFY_PUBKEY", pub_b64)
    load, reason = gate_plugin_load(p, "demo")
    assert load is True
    assert reason is None


def test_gate_preferred_refuses_tampered(tmp_path, monkeypatch):
    """Even in preferred mode, a PRESENT-but-WRONG signature is a
    hard fail — that's an active tamper signal, not the soft 'no key
    configured' case."""
    priv, pub_b64 = _gen_keypair()
    p = _build_plugin(tmp_path, "demo")
    _sign_plugin(p, priv)
    (p / "helper.py").write_text("X = 999\n")  # tamper
    monkeypatch.setenv("PLUGIN_VERIFY", "preferred")
    monkeypatch.setenv("PLUGIN_VERIFY_PUBKEY", pub_b64)
    load, reason = gate_plugin_load(p, "demo")
    assert load is False
    assert "signature check failed" in reason


def test_gate_required_refuses_unsigned(tmp_path, monkeypatch):
    """The hardening operating mode — no signature means no load."""
    _, pub_b64 = _gen_keypair()
    p = _build_plugin(tmp_path, "demo")
    monkeypatch.setenv("PLUGIN_VERIFY", "required")
    monkeypatch.setenv("PLUGIN_VERIFY_PUBKEY", pub_b64)
    load, reason = gate_plugin_load(p, "demo")
    assert load is False
    assert "signature check failed" in reason


def test_gate_required_allows_valid_signature(tmp_path, monkeypatch):
    priv, pub_b64 = _gen_keypair()
    p = _build_plugin(tmp_path, "demo")
    _sign_plugin(p, priv)
    monkeypatch.setenv("PLUGIN_VERIFY", "required")
    monkeypatch.setenv("PLUGIN_VERIFY_PUBKEY", pub_b64)
    load, reason = gate_plugin_load(p, "demo")
    assert load is True
    assert reason is None


def test_unknown_mode_defaults_to_off(monkeypatch):
    """A typo in PLUGIN_VERIFY shouldn't accidentally lock out an
    operator who wasn't intending to require signatures."""
    monkeypatch.setenv("PLUGIN_VERIFY", "strict")  # invalid
    assert get_verify_mode() == VerifyMode.OFF
