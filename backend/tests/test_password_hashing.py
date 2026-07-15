"""Password hashing contract tests for ``auth/password.py``.

The module is a thin bcrypt wrapper (``get_password_hash`` /
``verify_password``). These tests pin the properties callers depend on:

  * a hash verifies against its own plaintext and nothing else,
  * every hash is uniquely salted (same password → different digests),
  * the digest is a real bcrypt ``$2b$`` string, and
  * the *actual* bcrypt truncation behaviour the wrapper inherits (bcrypt
    only considers the first 72 bytes) — documented so a future switch to a
    pre-hash or a length guard shows up as a failing test rather than a
    silent behaviour change.
"""

from __future__ import annotations

from auth.password import get_password_hash, verify_password


def test_hash_verifies_against_correct_password():
    h = get_password_hash("Sup3rSecret!pw")
    assert verify_password("Sup3rSecret!pw", h) is True


def test_hash_rejects_wrong_password():
    h = get_password_hash("correct horse battery staple")
    assert verify_password("wrong password", h) is False


def test_hash_is_not_plaintext():
    h = get_password_hash("plaintext-check")
    assert h != "plaintext-check"
    assert "plaintext-check" not in h


def test_two_hashes_of_same_password_differ():
    """Random per-hash salt: identical inputs must not produce identical
    digests (otherwise a hash collision would leak password equality)."""
    a = get_password_hash("same-password")
    b = get_password_hash("same-password")
    assert a != b
    # ...but both still verify.
    assert verify_password("same-password", a)
    assert verify_password("same-password", b)


def test_hash_has_bcrypt_structure():
    h = get_password_hash("structural")
    # bcrypt digests are $2b$<cost>$<22-char-salt><31-char-hash>.
    assert h.startswith("$2b$")
    assert len(h) == 60


def test_empty_password_round_trips():
    h = get_password_hash("")
    assert verify_password("", h) is True
    assert verify_password("x", h) is False


def test_unicode_password_round_trips():
    pw = "pÄsswörd–🔐"
    h = get_password_hash(pw)
    assert verify_password(pw, h) is True
    assert verify_password("password", h) is False


def test_bcrypt_truncates_at_72_bytes():
    """Documented inherited behaviour: bcrypt only mixes in the first 72
    bytes, so two passwords sharing a 72-byte prefix verify against the same
    hash. This is NOT a wrapper feature — it's the truncation the module does
    not guard against. If a future change adds a pre-hash, this flips.
    """
    base = "A" * 72
    h = get_password_hash(base)
    # Same first 72 bytes, different 73rd byte → still verifies.
    assert verify_password(base + "DIFFERENT-TAIL", h) is True
    assert verify_password(base, h) is True
    # A difference within the first 72 bytes is honoured.
    assert verify_password("B" + "A" * 71, h) is False
