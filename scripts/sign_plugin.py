#!/usr/bin/env python3
"""Sign a RedWire plugin with an Ed25519 private key.

Companion to ``backend/utils/plugin_signature.py``. Produces the
``plugin.yaml.sig`` file the verifier expects, computed over the
same SHA-256-of-directory-contents the verifier checks.

Usage:
    # one-time keygen
    python scripts/sign_plugin.py keygen --out ./plugin-signing-key
    # → writes ./plugin-signing-key (private) + ./plugin-signing-key.pub (base64)

    # sign a plugin
    python scripts/sign_plugin.py sign \\
        --plugin-dir backend/plugins/shodan_enricher \\
        --key ./plugin-signing-key
    # → writes backend/plugins/shodan_enricher/plugin.yaml.sig

The public key (``plugin-signing-key.pub``) is what the operator
sets as the PLUGIN_VERIFY_PUBKEY env var on the RedWire backend.

Standalone CLI by design — no FastAPI / SQLAlchemy / RedWire deps,
just ``cryptography``. Run from any environment that has Python +
cryptography installed.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import os
import sys
from pathlib import Path


# Mirror the verifier's exclude rules exactly.
_HASH_EXCLUDES = {"plugin.yaml.sig", "plugin.yml.sig"}
_HASH_EXCLUDE_DIRS = {"__pycache__"}


def _iter_hashable_files(plugin_dir: Path) -> list[Path]:
    out: list[Path] = []
    for root, dirs, files in os.walk(plugin_dir):
        dirs[:] = [d for d in dirs if d not in _HASH_EXCLUDE_DIRS]
        for name in files:
            if name in _HASH_EXCLUDES:
                continue
            out.append(Path(root) / name)
    out.sort(key=lambda p: p.relative_to(plugin_dir).as_posix())
    return out


def compute_manifest_digest(plugin_dir: Path) -> bytes:
    h = hashlib.sha256()
    for f in _iter_hashable_files(plugin_dir):
        rel = f.relative_to(plugin_dir).as_posix().encode("utf-8")
        h.update(rel)
        h.update(b"\x00")
        with open(f, "rb") as fp:
            while True:
                chunk = fp.read(64 * 1024)
                if not chunk:
                    break
                h.update(chunk)
        h.update(b"\x00")
    return h.digest()


def cmd_keygen(args: argparse.Namespace) -> int:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization

    out = Path(args.out)
    if out.exists() and not args.force:
        print(f"refusing to overwrite {out} (pass --force to replace)", file=sys.stderr)
        return 2

    priv = Ed25519PrivateKey.generate()
    priv_bytes = priv.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    out.write_bytes(base64.b64encode(priv_bytes))
    os.chmod(out, 0o600)

    pub = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    pub_b64 = base64.b64encode(pub).decode("ascii")
    pub_path = out.with_suffix(out.suffix + ".pub")
    pub_path.write_text(pub_b64 + "\n")

    print(f"wrote private key: {out}")
    print(f"wrote public key:  {pub_path}")
    print()
    print("Configure the RedWire backend with:")
    print(f"  PLUGIN_VERIFY_PUBKEY={pub_b64}")
    print(f"  PLUGIN_VERIFY=preferred   # or required")
    return 0


def cmd_sign(args: argparse.Namespace) -> int:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    plugin_dir = Path(args.plugin_dir).resolve()
    if not plugin_dir.is_dir():
        print(f"not a directory: {plugin_dir}", file=sys.stderr)
        return 2
    if not (plugin_dir / "plugin.yaml").exists() and not (plugin_dir / "plugin.yml").exists():
        print(f"no plugin.yaml in {plugin_dir}", file=sys.stderr)
        return 2

    key_path = Path(args.key)
    if not key_path.is_file():
        print(f"key file not found: {key_path}", file=sys.stderr)
        return 2

    try:
        priv_b64 = key_path.read_text(encoding="utf-8").strip()
        priv_bytes = base64.b64decode(priv_b64, validate=True)
        priv = Ed25519PrivateKey.from_private_bytes(priv_bytes)
    except Exception as e:
        print(f"could not parse key file: {e}", file=sys.stderr)
        return 2

    digest = compute_manifest_digest(plugin_dir)
    sig_bytes = priv.sign(digest)
    sig_b64 = base64.b64encode(sig_bytes).decode("ascii")

    sig_path = plugin_dir / "plugin.yaml.sig"
    sig_path.write_text(sig_b64 + "\n")
    print(f"wrote signature: {sig_path}")
    print(f"manifest digest: {digest.hex()}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_keygen = sub.add_parser("keygen", help="Generate a new Ed25519 signing key")
    p_keygen.add_argument("--out", required=True, help="Output path for the private key")
    p_keygen.add_argument("--force", action="store_true", help="Overwrite existing key")
    p_keygen.set_defaults(func=cmd_keygen)

    p_sign = sub.add_parser("sign", help="Sign a plugin directory")
    p_sign.add_argument("--plugin-dir", required=True, help="Path to plugin directory")
    p_sign.add_argument("--key", required=True, help="Path to private key file")
    p_sign.set_defaults(func=cmd_sign)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
