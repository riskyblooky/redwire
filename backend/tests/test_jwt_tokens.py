"""Core JWT token contract tests for ``auth/jwt.py``.

Covers the three layers the module is responsible for:

  * ``create_access_token`` / ``create_refresh_token`` — the claim set every
    issued token must carry (``exp``, ``iat``, ``type``, ``jti``) and the
    explicit-type override used for password-reset / e-mail tokens.
  * ``decode_token`` — signature + algorithm pinning and the mandatory-claim
    gate (``sub``/``type``/``jti``/``exp``). The jti/type requirement is the
    GHSA-832g-v288-v593 deploy-time invalidation, so a token missing either
    must be rejected even when the signature is valid.
  * ``blacklist_token`` / ``is_token_blacklisted`` / ``revoke_all_user_tokens``
    — the Redis-backed revocation, exercised against the container's real
    Redis for the happy-path round-trips and forced fail-CLOSED by stubbing
    ``_get_redis`` to ``None``.
"""

from __future__ import annotations

import time
import uuid

import pytest
from jose import jwt as jose_jwt

from auth import jwt as authjwt


# ── helpers ───────────────────────────────────────────────────────────────


def _raw(payload: dict, *, algorithm: str | None = None) -> str:
    """Encode a payload directly with the module's secret so we can craft
    tokens the public helpers would never produce (missing claims, wrong alg)."""
    return jose_jwt.encode(
        payload,
        authjwt.SECRET_KEY,
        algorithm=algorithm or authjwt.ALGORITHM,
    )


def _future() -> int:
    return int(time.time()) + 3600


# ── create_access_token ───────────────────────────────────────────────────


def test_access_token_carries_full_claim_set():
    tok = authjwt.create_access_token({"sub": "user-1"})
    payload = authjwt.decode_token(tok)
    assert payload is not None
    assert payload["sub"] == "user-1"
    assert payload["type"] == "access"
    assert "jti" in payload and payload["jti"]
    assert "exp" in payload
    assert "iat" in payload
    assert payload["iat"] <= payload["exp"]


def test_access_token_jti_is_unique_per_token():
    a = authjwt.decode_token(authjwt.create_access_token({"sub": "u"}))
    b = authjwt.decode_token(authjwt.create_access_token({"sub": "u"}))
    assert a["jti"] != b["jti"]


def test_access_token_preserves_explicit_type():
    """A caller minting a password-reset token sets type in the data; the
    helper must not clobber it back to 'access'."""
    tok = authjwt.create_access_token({"sub": "u", "type": "password_reset"})
    payload = authjwt.decode_token(tok)
    assert payload["type"] == "password_reset"


def test_access_token_honours_explicit_expiry():
    from datetime import timedelta

    tok = authjwt.create_access_token({"sub": "u"}, expires_delta=timedelta(seconds=5))
    payload = authjwt.decode_token(tok)
    # 5s window → exp - iat should be ~5, definitely well under the 30-min default.
    assert 0 < payload["exp"] - payload["iat"] <= 10


# ── create_refresh_token ──────────────────────────────────────────────────


def test_refresh_token_is_typed_refresh_with_jti():
    tok = authjwt.create_refresh_token({"sub": "user-9"})
    payload = authjwt.decode_token(tok)
    assert payload["type"] == "refresh"
    assert payload["sub"] == "user-9"
    assert payload["jti"]
    # Refresh lifetime is hours, far beyond the 30-min access default.
    assert payload["exp"] - payload["iat"] > 3600


# ── decode_token: valid round-trip + rejections ───────────────────────────


def test_decode_rejects_tampered_signature():
    tok = authjwt.create_access_token({"sub": "u"})
    head, body, sig = tok.split(".")
    # Flip a leading signature char (not the last — its trailing base64 bits
    # are unused, so flipping it can decode to identical bytes).
    flipped = ("A" if sig[0] != "A" else "B") + sig[1:]
    assert authjwt.decode_token(f"{head}.{body}.{flipped}") is None


def test_decode_rejects_wrong_algorithm():
    """decode pins algorithms=[HS256]; a token signed with a different alg
    must be refused (algorithm-confusion defence)."""
    tok = _raw(
        {"sub": "u", "type": "access", "jti": str(uuid.uuid4()), "exp": _future()},
        algorithm="HS512",
    )
    assert authjwt.decode_token(tok) is None


def test_decode_rejects_missing_jti():
    tok = _raw({"sub": "u", "type": "access", "exp": _future()})
    assert authjwt.decode_token(tok) is None


def test_decode_rejects_missing_type():
    tok = _raw({"sub": "u", "jti": str(uuid.uuid4()), "exp": _future()})
    assert authjwt.decode_token(tok) is None


def test_decode_rejects_missing_sub():
    tok = _raw({"type": "access", "jti": str(uuid.uuid4()), "exp": _future()})
    assert authjwt.decode_token(tok) is None


def test_decode_rejects_missing_exp():
    tok = _raw({"sub": "u", "type": "access", "jti": str(uuid.uuid4())})
    assert authjwt.decode_token(tok) is None


def test_decode_rejects_expired():
    tok = _raw(
        {
            "sub": "u",
            "type": "access",
            "jti": str(uuid.uuid4()),
            "exp": int(time.time()) - 10,
        }
    )
    assert authjwt.decode_token(tok) is None


def test_decode_rejects_garbage():
    assert authjwt.decode_token("not.a.jwt") is None


# ── Redis-backed revocation: real round-trips ─────────────────────────────


def test_blacklist_round_trip():
    """A freshly minted token isn't blacklisted; after blacklist_token it is."""
    tok = authjwt.create_access_token({"sub": str(uuid.uuid4())})
    assert authjwt.is_token_blacklisted(tok) is False
    assert authjwt.blacklist_token(tok) is True
    assert authjwt.is_token_blacklisted(tok) is True


def test_blacklist_missing_jti_returns_false():
    """A token with no jti can't be keyed into the per-token blacklist."""
    tok = _raw({"sub": "u", "type": "access", "exp": _future()})
    assert authjwt.blacklist_token(tok) is False


def test_revoke_all_user_tokens_cutoff():
    """revoke_all sets a per-user cutoff: tokens issued before it are dead,
    tokens issued after it survive."""
    user_id = str(uuid.uuid4())
    now = int(time.time())
    before = _raw(
        {
            "sub": user_id,
            "type": "access",
            "jti": str(uuid.uuid4()),
            "iat": now - 100,
            "exp": now + 3600,
        }
    )
    after = _raw(
        {
            "sub": user_id,
            "type": "access",
            "jti": str(uuid.uuid4()),
            "iat": now + 100,
            "exp": now + 3600,
        }
    )
    # Not revoked yet — neither is blacklisted.
    assert authjwt.is_token_blacklisted(before) is False
    assert authjwt.revoke_all_user_tokens(user_id) is True
    # Issued-before token is now rejected; issued-after token still lives.
    assert authjwt.is_token_blacklisted(before) is True
    assert authjwt.is_token_blacklisted(after) is False


# ── Redis-backed revocation: fail CLOSED when Redis is unavailable ─────────


def test_is_token_blacklisted_fails_closed_without_redis(monkeypatch):
    """The GHSA-832g invariant: if we can't reach Redis we cannot prove a
    token is live, so we must treat it as revoked."""
    monkeypatch.setattr(authjwt, "_get_redis", lambda: None)
    tok = authjwt.create_access_token({"sub": "u"})
    assert authjwt.is_token_blacklisted(tok) is True


def test_blacklist_token_reports_failure_without_redis(monkeypatch):
    """A failed revocation must return False so the caller can surface it —
    a silent success would leave the token live."""
    monkeypatch.setattr(authjwt, "_get_redis", lambda: None)
    tok = authjwt.create_access_token({"sub": "u"})
    assert authjwt.blacklist_token(tok) is False


def test_revoke_all_reports_failure_without_redis(monkeypatch):
    monkeypatch.setattr(authjwt, "_get_redis", lambda: None)
    assert authjwt.revoke_all_user_tokens("user-x") is False


def test_is_token_blacklisted_fails_closed_on_decode_error():
    """A malformed token that raises inside the check must also fail closed,
    not fall through to 'not blacklisted'."""
    # Real Redis is up here, so the fail-closed path is the decode exception.
    assert authjwt.is_token_blacklisted("garbage-not-a-jwt") is True
