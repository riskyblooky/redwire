"""GHSA-fp33-983q-99r9 — pre-auth rollup fix regressions.

Three of six sub-issues shipped as fixes:

  #1 (CWE-208) Login now runs bcrypt exactly once per request so
     response time doesn't reveal user existence.
  #2 (CWE-204) Registration validates the code BEFORE user-uniqueness
     checks and returns a single generic error for every pre-create
     failure so username/email enumeration is closed at the register
     surface.
  #4 (CWE-1240) Password fields on SET paths (UserCreate.password,
     UserPasswordUpdate.new_password) reject inputs over 72 bytes so
     bcrypt's silent truncation can't create hash collisions between
     different plaintexts.

Three declined as intended-by-design (see memories):

  #3 OpenAPI/Swagger docs unauth — nginx doesn't publish backend port
  #5 JWT lacks aud/iss — identity resolved from sub via DB
  #6 Registration codes plaintext — low-value open-reg convenience knob
"""

from __future__ import annotations

import os

import pytest
from pydantic import ValidationError

# TOTP + vault crypto want their env vars set at import; provide throwaway
# ones so schema/router imports don't blow up in the test process.
from cryptography.fernet import Fernet
os.environ.setdefault("TOTP_ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ.setdefault("VAULT_ENCRYPTION_KEY", Fernet.generate_key().decode())

from schemas.user import (
    UserCreate,
    UserPasswordUpdate,
    _validate_password_bcrypt_safe,
)


# ── Issue 4: bcrypt-safe byte length ─────────────────────────────────


class TestPasswordByteLength:
    """Pin the byte-cap so a future refactor can't accidentally revert
    to the character-count check (which under-caps multi-byte
    passwords) or drop the validator entirely."""

    def test_short_password_accepted(self):
        assert _validate_password_bcrypt_safe("password123") == "password123"

    def test_exactly_72_bytes_accepted(self):
        pw = "a" * 72
        assert _validate_password_bcrypt_safe(pw) == pw

    def test_73_bytes_rejected(self):
        # One byte over the bcrypt limit — must reject with the
        # explanatory message so the user knows to shorten rather
        # than assume the password is being accepted-and-truncated
        # (the pre-fix behaviour).
        with pytest.raises(ValueError, match="72-byte limit"):
            _validate_password_bcrypt_safe("a" * 73)

    def test_multibyte_over_72_rejected(self):
        # 20 emoji × 4 bytes each = 80 bytes; well under 72 chars but
        # over the byte cap. The pre-fix state would bcrypt-truncate
        # this to whatever the first 72 bytes are — creating collision
        # opportunities across different plaintexts that share a
        # 72-byte prefix.
        pw = "🔑" * 20
        assert len(pw) == 20  # sanity
        assert len(pw.encode("utf-8")) > 72
        with pytest.raises(ValueError, match="72-byte limit"):
            _validate_password_bcrypt_safe(pw)

    def test_message_shows_actual_byte_count(self):
        pw = "🔑" * 20
        with pytest.raises(ValueError) as exc:
            _validate_password_bcrypt_safe(pw)
        # 20 emoji = 80 bytes. The error message must include the
        # actual count so the user can size their password
        # accordingly.
        assert "80" in str(exc.value)


class TestUserCreatePasswordBinding:
    """UserCreate.password gets the bcrypt-safe validator. Regression
    pin against a future edit dropping the binding."""

    def test_create_rejects_long_password(self):
        with pytest.raises(ValidationError):
            UserCreate(username="alice", email="a@example.com", password="a" * 100)

    def test_create_accepts_normal_password(self):
        u = UserCreate(username="alice", email="a@example.com", password="password123")
        assert u.password == "password123"

    def test_create_accepts_72_byte_password(self):
        pw = "a" * 72
        u = UserCreate(username="alice", email="a@example.com", password=pw)
        assert u.password == pw


class TestPasswordUpdateBindings:
    """new_password gets the validator; old_password does NOT (legacy
    users with long passwords must still be able to change them)."""

    def test_new_password_over_72_rejected(self):
        with pytest.raises(ValidationError):
            UserPasswordUpdate(old_password="anything", new_password="a" * 100)

    def test_old_password_over_72_accepted(self):
        # Regression pin — an operator whose pre-fix password is 100
        # bytes must still be able to submit it to VERIFY-then-change.
        # bcrypt truncation on verify is symmetric, so the flow works.
        upd = UserPasswordUpdate(old_password="a" * 100, new_password="new_password_123")
        assert upd.old_password == "a" * 100

    def test_new_password_normal_accepted(self):
        upd = UserPasswordUpdate(
            old_password="old_password", new_password="new_password_123",
        )
        assert upd.new_password == "new_password_123"
