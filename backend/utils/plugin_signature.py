"""Ed25519 detached-signature verification for plugins.

GHSA-2rv7-jv5j-m4jg follow-up. Plugin code runs in-process with full
backend privileges (no sandbox); the load path is admin-gated but
"admin account" is the entire keychain. A compromised admin or a
tampered archive at upload is arbitrary code execution. Signature
verification gives the operator a separate trust anchor — the
admin account uploads, the signing key authorises.

Manifest of trust: a plugin's signature commits to
  H = SHA-256("plugin.yaml" || NUL || <bytes of plugin.yaml> || NUL ||
              "<relpath>" || NUL || <bytes> || NUL || ...)
for every file in the plugin directory (sorted by relpath) EXCEPT the
signature file itself and ``__pycache__``. Sorting + NUL-framing
defeats shuffle / collision attempts at the canonicalisation layer.

The signature itself is base64-encoded Ed25519 written to
``plugin.yaml.sig`` next to the manifest. ``sign_plugin.py`` (in
``scripts/``) produces it from a private key the author holds; this
module verifies it against the public key the operator configures
via ``PLUGIN_VERIFY_PUBKEY`` (base64 Ed25519 verify key) or via the
admin setting of the same name.

Operating modes (env var ``PLUGIN_VERIFY``):
  - ``off``       — current behaviour, no verification (default for
                    upgrade compatibility with existing in-tree plugins).
  - ``preferred`` — verify when both pubkey + signature present; warn
                    + load on missing signature; refuse to load on
                    signature mismatch or unparseable signature.
  - ``required`` — refuse to load any plugin without a valid signature.

Fail-closed at the operator's discretion. Default off is deliberate
so this commit doesn't break currently-loading deployments; flipping
to ``required`` is a per-deployment hardening step the operator
opts into.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class VerifyMode(str, Enum):
    OFF = "off"
    PREFERRED = "preferred"
    REQUIRED = "required"


# Files that never participate in the manifest hash. ``__pycache__``
# is build output; ``plugin.yaml.sig`` is the signature itself and
# including it would create a self-referential cycle.
_HASH_EXCLUDES = {"plugin.yaml.sig", "plugin.yml.sig"}
_HASH_EXCLUDE_DIRS = {"__pycache__"}

_SIGNATURE_FILENAMES = ("plugin.yaml.sig", "plugin.yml.sig")


def get_verify_mode() -> VerifyMode:
    """Read PLUGIN_VERIFY env var. Unknown values default to OFF so
    a typo doesn't accidentally lock out an operator who wasn't
    intending to require signatures."""
    raw = os.getenv("PLUGIN_VERIFY", "off").strip().lower()
    try:
        return VerifyMode(raw)
    except ValueError:
        logger.warning(
            "PLUGIN_VERIFY=%r is not one of off/preferred/required; "
            "defaulting to off",
            raw,
        )
        return VerifyMode.OFF


def get_pubkey_b64() -> Optional[str]:
    """The operator's Ed25519 verify key, base64-encoded. Returned as
    the raw string so the verifier can fail with a clear error if it
    isn't parseable."""
    raw = (os.getenv("PLUGIN_VERIFY_PUBKEY", "") or "").strip()
    return raw or None


def _iter_hashable_files(plugin_dir: Path) -> list[Path]:
    """Return a deterministic sorted list of files that participate in
    the manifest hash. Sorting uses POSIX-style relpaths so the hash
    is OS-independent (Windows backslashes don't change the canonical
    form)."""
    out: list[Path] = []
    for root, dirs, files in os.walk(plugin_dir):
        # Exclude in-place — os.walk respects dirs mutations.
        dirs[:] = [d for d in dirs if d not in _HASH_EXCLUDE_DIRS]
        for name in files:
            if name in _HASH_EXCLUDES:
                continue
            out.append(Path(root) / name)
    out.sort(key=lambda p: p.relative_to(plugin_dir).as_posix())
    return out


def compute_manifest_digest(plugin_dir: Path) -> bytes:
    """SHA-256 over the canonicalised directory contents.

    The digest input is a NUL-framed sequence of (relpath, contents)
    pairs sorted by relpath. NUL is not a legal character in either
    POSIX or NTFS filenames, so it can't appear inside a relpath —
    framing is unambiguous.
    """
    h = hashlib.sha256()
    for f in _iter_hashable_files(plugin_dir):
        rel = f.relative_to(plugin_dir).as_posix().encode("utf-8")
        h.update(rel)
        h.update(b"\x00")
        with open(f, "rb") as fp:
            # Stream so large vendored files (rare but possible) don't
            # blow memory. 64 KiB matches the storage helper.
            while True:
                chunk = fp.read(64 * 1024)
                if not chunk:
                    break
                h.update(chunk)
        h.update(b"\x00")
    return h.digest()


def find_signature_file(plugin_dir: Path) -> Optional[Path]:
    """Locate the signature file in the plugin directory. Returns
    None if absent (caller decides what to do based on VerifyMode)."""
    for name in _SIGNATURE_FILENAMES:
        candidate = plugin_dir / name
        if candidate.is_file():
            return candidate
    return None


def verify_plugin_signature(plugin_dir: Path) -> tuple[bool, Optional[str]]:
    """Verify the plugin's signature against ``PLUGIN_VERIFY_PUBKEY``.

    Returns (ok, reason). ``ok=True`` means the signature parsed +
    matched the configured pubkey + covered the on-disk contents.
    ``reason`` is a human-readable explanation for the loader to
    surface as the plugin's load error / log line.

    Failure modes (all return ok=False):
      - No pubkey configured
      - No signature file in the plugin dir
      - Signature file unreadable or not base64-decodable
      - Wrong length (Ed25519 sigs are exactly 64 bytes)
      - Verify mismatch (tampered or wrong key)
    """
    pubkey_b64 = get_pubkey_b64()
    if not pubkey_b64:
        return False, "PLUGIN_VERIFY_PUBKEY is not set"

    try:
        pubkey_bytes = base64.b64decode(pubkey_b64, validate=True)
    except Exception as e:
        return False, f"PLUGIN_VERIFY_PUBKEY is not valid base64: {e}"

    sig_path = find_signature_file(plugin_dir)
    if sig_path is None:
        return False, "no signature file (expected plugin.yaml.sig)"

    try:
        sig_b64 = sig_path.read_text(encoding="utf-8").strip()
        sig_bytes = base64.b64decode(sig_b64, validate=True)
    except Exception as e:
        return False, f"signature file not parseable: {e}"

    if len(sig_bytes) != 64:
        return False, f"signature is {len(sig_bytes)} bytes; Ed25519 is 64"

    # ``cryptography`` is already a backend dep (used by Fernet vault
    # encryption); reuse it here so we don't pull a second crypto lib.
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PublicKey,
        )
        from cryptography.exceptions import InvalidSignature
    except ImportError as e:
        return False, f"cryptography library unavailable: {e}"

    try:
        pubkey = Ed25519PublicKey.from_public_bytes(pubkey_bytes)
    except Exception as e:
        return False, f"PLUGIN_VERIFY_PUBKEY is not a valid Ed25519 key: {e}"

    digest = compute_manifest_digest(plugin_dir)

    try:
        pubkey.verify(sig_bytes, digest)
    except InvalidSignature:
        return False, "signature does not match plugin contents"
    except Exception as e:
        return False, f"signature verification raised: {e}"

    return True, "signature verified"


def gate_plugin_load(plugin_dir: Path, plugin_id: str) -> tuple[bool, Optional[str]]:
    """Apply the configured ``PLUGIN_VERIFY`` mode to decide whether
    ``plugin_id`` is allowed to load.

    Returns (should_load, reason). ``should_load=False`` means the
    loader skips this plugin and records ``reason`` on the
    ``LoadedPlugin.error`` field so the admin UI can surface it.
    """
    mode = get_verify_mode()

    if mode == VerifyMode.OFF:
        return True, None

    ok, reason = verify_plugin_signature(plugin_dir)

    if ok:
        return True, None

    if mode == VerifyMode.PREFERRED:
        # No pubkey or no signature → load with a warning. A mismatch
        # or a bad signature is still fatal in PREFERRED mode — only
        # the "infrastructure missing" cases get the soft pass.
        soft_fail_substrings = (
            "PLUGIN_VERIFY_PUBKEY is not set",
            "no signature file",
        )
        if any(s in (reason or "") for s in soft_fail_substrings):
            logger.warning(
                "plugin-verify[preferred]: loading %s without signature: %s",
                plugin_id, reason,
            )
            return True, None
        # Otherwise (bad sig, wrong key, mismatch) — refuse even in
        # preferred mode. A present-but-wrong signature is a stronger
        # signal than absence.
        return False, f"signature check failed: {reason}"

    # REQUIRED — refuse on any failure.
    return False, f"signature check failed: {reason}"
