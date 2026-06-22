"""Recovery / backup codes for 2FA self-service recovery.

GHSA-vm6w-9wm5-q367 follow-up. Issued at successful
``/auth/totp/verify-setup``, shown to the user exactly once in that
response, stored only as bcrypt hashes. Consumed at ``/auth/verify-2fa``
when the user submits a recovery-code-shaped value instead of a TOTP
code; the matching row's ``used_at`` flips to the consumption
timestamp.

Code format:
    ``XXXX-XXXX`` — eight alphanumeric characters from an
    ambiguous-glyph-free alphabet, split by a hyphen at the midpoint
    for readability. The displayed alphabet drops ``0/O`` and
    ``1/I/l`` to avoid handwritten-transcription errors. ~6.5×10¹¹
    possible codes — well above brute-force given the per-route
    rate limit at ``/auth/verify-2fa``.

Number of codes:
    10 per user (matches GitHub / GitLab / Google / 1Password
    convention). Comfortable to write down on a single line.

Disjoint from TOTP shape:
    TOTP codes are RFC 6238 — always 6-8 *digits*. Recovery codes
    always contain at least one letter. ``looks_like_recovery_code``
    below uses that property so the verify-2fa endpoint can dispatch
    on a single submitted value without needing two endpoints.
"""

from __future__ import annotations

import secrets
from typing import List


# Ambiguous-glyph-free alphabet — dropped 0, O, 1, I, l for handwritten
# transcription. 31 characters; 31⁸ ≈ 8.5×10¹¹ codes; still ≈ 40 bits
# of entropy per code, plenty given the per-user verify-2fa rate limit.
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"

# 8 alnum characters in two 4-char groups, separated by a hyphen at the
# midpoint. The hyphen is purely display — comparisons normalise it out.
_GROUP_LEN = 4
_NUM_GROUPS = 2
_CODE_LEN = _GROUP_LEN * _NUM_GROUPS  # 8

# Number of codes issued per enrollment / regeneration.
NUM_CODES = 10


def generate_code() -> str:
    """Generate a single ``XXXX-XXXX`` recovery code from the
    ambiguous-glyph-free alphabet using ``secrets.choice``."""
    chars = [secrets.choice(_ALPHABET) for _ in range(_CODE_LEN)]
    return "-".join(
        "".join(chars[i * _GROUP_LEN : (i + 1) * _GROUP_LEN])
        for i in range(_NUM_GROUPS)
    )


def generate_codes(n: int = NUM_CODES) -> List[str]:
    """Generate a fresh batch of ``n`` recovery codes (default 10).

    Collisions inside one batch are astronomically unlikely given the
    alphabet + length, but we dedup defensively so a freak collision
    doesn't ship a user 9 unique + 1 duplicate.
    """
    out: set[str] = set()
    while len(out) < n:
        out.add(generate_code())
    return sorted(out)


def normalise(submitted: str) -> str:
    """Normalise a user-submitted code for comparison: strip
    whitespace, drop hyphens, uppercase. So ``k9q3 7xhb`` →
    ``K9Q37XHB`` matches ``K9Q3-7XHB``."""
    if not submitted:
        return ""
    return submitted.replace("-", "").replace(" ", "").strip().upper()


def looks_like_recovery_code(submitted: str) -> bool:
    """Cheap shape test used by the verify-2fa dispatcher to decide
    whether to walk the recovery-code path or the TOTP path. Recovery
    codes contain at least one letter from the alphabet; TOTP codes
    are RFC 6238 digits-only. The two shapes are disjoint."""
    if not submitted:
        return False
    n = normalise(submitted)
    if len(n) != _CODE_LEN:
        return False
    # All characters must be in our alphabet AND the value must contain
    # at least one letter (to disambiguate from a digits-only TOTP that
    # happens to also be 8 chars long, e.g. a custom TOTP setup).
    if not all(c in _ALPHABET for c in n):
        return False
    return any(c.isalpha() for c in n)


def hash_code(plaintext: str) -> str:
    """bcrypt-hash a recovery code. Uses ``auth.password.get_password_hash``
    so the cost factor matches the password store (currently 12). The
    submitted code is normalised before hashing so paste-with-spaces or
    paste-without-hyphens still verifies."""
    from auth.password import get_password_hash
    return get_password_hash(normalise(plaintext))


def verify_code(submitted: str, stored_hash: str) -> bool:
    """Constant-time bcrypt verify against a single stored hash, with
    the same normalisation as ``hash_code``. Callers iterate stored
    hashes until one matches (or none do).

    Note: with 10 hashes × bcrypt cost 12 (~100ms each), a worst-case
    miss is ~1s of wall clock. That's fine — recovery codes are used
    rarely, the per-route rate limit on ``/verify-2fa`` (5/min) caps
    abuse, and the cost is the same shape as the password verifier
    callers already use.
    """
    from auth.password import verify_password
    return verify_password(normalise(submitted), stored_hash)
