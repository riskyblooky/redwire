"""Helper regressions for the 2FA recovery code module.

GHSA-vm6w-9wm5-q367 follow-up. The code-shape contract is what the
verify-2fa dispatcher relies on to route between TOTP and recovery
paths; the hash/verify round-trip is what makes the codes safely
storable; the normalisation rules are what let a user paste a code
with or without the displayed hyphen / surrounding whitespace and
have it still match.
"""

from __future__ import annotations

import re

import pytest

from auth.recovery_codes import (
    NUM_CODES,
    generate_code,
    generate_codes,
    hash_code,
    looks_like_recovery_code,
    normalise,
    verify_code,
)


# ── format / generation ──────────────────────────────────────────────


_CODE_RE = re.compile(r"^[ABCDEFGHJKMNPQRSTUVWXYZ23456789]{4}-[ABCDEFGHJKMNPQRSTUVWXYZ23456789]{4}$")


def test_generate_code_shape():
    for _ in range(20):
        c = generate_code()
        assert _CODE_RE.fullmatch(c), f"unexpected shape: {c!r}"


def test_generate_codes_default_count_and_unique():
    batch = generate_codes()
    assert len(batch) == NUM_CODES
    assert len(set(batch)) == NUM_CODES


def test_generate_codes_avoids_ambiguous_glyphs():
    """Alphabet must skip 0/O, 1/I/l to prevent transcription errors."""
    forbidden = set("0O1Il")
    batch = generate_codes(50)
    joined = "".join(batch).replace("-", "")
    assert not (forbidden & set(joined)), "ambiguous glyphs in generated codes"


def test_generate_codes_custom_count():
    assert len(generate_codes(3)) == 3
    assert len(generate_codes(25)) == 25


# ── shape detection (dispatcher contract) ────────────────────────────


@pytest.mark.parametrize("good", [
    "K9Q3-7XHB",
    "k9q3-7xhb",
    "K9Q3 7XHB",
    "K9Q37XHB",
    "  K9Q3-7XHB  ",
])
def test_looks_like_recovery_code_accepts_recovery_shapes(good):
    assert looks_like_recovery_code(good)


@pytest.mark.parametrize("bad", [
    "",
    None,
    "123456",          # 6-digit TOTP
    "1234567",         # 7-digit TOTP (RFC 6238 allows 7-8)
    "12345678",        # 8-digit all-digit TOTP — must NOT be detected as recovery
    "K9Q3-7XH",        # too short (7 alnum)
    "K9Q3-7XHBQ",      # too long (9 alnum)
    "K9Q3-O7XH",       # contains forbidden alphabet char (O)
    "K9Q3-7XH!",       # contains punctuation outside the alphabet
])
def test_looks_like_recovery_code_rejects_non_recovery_shapes(bad):
    assert not looks_like_recovery_code(bad)


def test_recovery_and_totp_shapes_are_disjoint():
    """Strict invariant: no TOTP code (1-8 digits) should be classified
    as a recovery code. If this fails, the verify-2fa dispatcher will
    route a TOTP submission down the recovery path."""
    for length in range(1, 9):
        for digits in ("0" * length, "9" * length, "1234567"[:length]):
            assert not looks_like_recovery_code(digits), (
                f"{digits!r} ({length} digits) misclassified as recovery code"
            )


# ── normalisation ────────────────────────────────────────────────────


@pytest.mark.parametrize("inp,expected", [
    ("K9Q3-7XHB", "K9Q37XHB"),
    ("k9q3-7xhb", "K9Q37XHB"),
    ("K9Q3 7XHB", "K9Q37XHB"),
    ("  K9Q3-7XHB  ", "K9Q37XHB"),
    ("K9Q37XHB", "K9Q37XHB"),
    ("", ""),
])
def test_normalise(inp, expected):
    assert normalise(inp) == expected


# ── hash / verify round-trip ────────────────────────────────────────


def test_hash_verify_round_trip_for_canonical_form():
    h = hash_code("K9Q3-7XHB")
    assert verify_code("K9Q3-7XHB", h)


def test_verify_accepts_all_normalisable_forms():
    h = hash_code("K9Q3-7XHB")
    for variant in ("k9q3-7xhb", "K9Q37XHB", "K9Q3 7XHB", "  k9q37xhb  "):
        assert verify_code(variant, h), f"{variant!r} should match"


def test_verify_rejects_wrong_code():
    h = hash_code("K9Q3-7XHB")
    assert not verify_code("AAAA-BBBB", h)
    assert not verify_code("K9Q3-7XHA", h)  # one char off


def test_each_hash_is_distinct_for_same_plaintext():
    """bcrypt salt — same plaintext produces different hashes. Pin
    this so we don't accidentally swap to an unsalted scheme."""
    h1 = hash_code("K9Q3-7XHB")
    h2 = hash_code("K9Q3-7XHB")
    assert h1 != h2
    # Both still verify.
    assert verify_code("K9Q3-7XHB", h1)
    assert verify_code("K9Q3-7XHB", h2)
