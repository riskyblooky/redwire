"""TOTP verification contract tests for ``auth/totp.py``.

Focus is the security-load-bearing verifier, ``verify_totp_code``:

  * a code accepted within the ±1-step drift window returns the matched step,
  * a wrong code returns None,
  * and — the GHSA-xqfh-2j9p-vmff replay defence — a code whose matched step
    is ``<= last_timestep`` is refused, including the subtle case where an
    attacker replays *last* window's code through the drift tolerance after
    the current step has already been consumed.

Time is frozen (monkeypatching ``auth.totp.time.time``) so the step maths is
deterministic and never straddles a 30-second boundary mid-test.
"""

from __future__ import annotations

import base64

import pyotp
import pytest

from auth import totp as totp_mod
from auth.totp import (
    generate_totp_secret,
    get_totp_uri,
    verify_totp_code,
)

INTERVAL = 30
FIXED_NOW = 1_700_000_000  # arbitrary fixed epoch; step = FIXED_NOW // 30


@pytest.fixture
def frozen_time(monkeypatch):
    monkeypatch.setattr(totp_mod.time, "time", lambda: FIXED_NOW)
    return FIXED_NOW


def _code_for_step_offset(secret: str, offset: int) -> str:
    """Produce the code a genuine authenticator would show for the current
    step + offset, matching the module's counter_offset semantics."""
    return pyotp.TOTP(secret).at(FIXED_NOW + offset * INTERVAL)


# ── secret + provisioning URI ─────────────────────────────────────────────


def test_generate_secret_is_valid_base32():
    secret = generate_totp_secret()
    assert isinstance(secret, str)
    # pyotp uses 32-char base32 secrets; must decode cleanly and be usable.
    base64.b32decode(secret)
    # A brand-new secret can immediately drive a TOTP.
    assert len(pyotp.TOTP(secret).now()) == 6


def test_generate_secret_is_random():
    assert generate_totp_secret() != generate_totp_secret()


def test_provisioning_uri_shape():
    secret = generate_totp_secret()
    uri = get_totp_uri(secret, "alice@example.com")
    assert uri.startswith("otpauth://totp/")
    assert "issuer=RedWire" in uri
    assert f"secret={secret}" in uri
    # The account name is URL-encoded into the label.
    assert "alice" in uri


# ── verify_totp_code: happy path + drift window ───────────────────────────


def test_verify_current_code_returns_current_step(frozen_time):
    secret = generate_totp_secret()
    step = verify_totp_code(secret, _code_for_step_offset(secret, 0))
    assert step == FIXED_NOW // INTERVAL


def test_verify_accepts_previous_step_within_window(frozen_time):
    secret = generate_totp_secret()
    step = verify_totp_code(secret, _code_for_step_offset(secret, -1))
    assert step == FIXED_NOW // INTERVAL - 1


def test_verify_accepts_next_step_within_window(frozen_time):
    secret = generate_totp_secret()
    step = verify_totp_code(secret, _code_for_step_offset(secret, +1))
    assert step == FIXED_NOW // INTERVAL + 1


def test_verify_rejects_wrong_code(frozen_time):
    secret = generate_totp_secret()
    # A code two steps out is beyond the ±1 window → rejected.
    assert verify_totp_code(secret, _code_for_step_offset(secret, +2)) is None


def test_verify_rejects_non_numeric_code(frozen_time):
    secret = generate_totp_secret()
    assert verify_totp_code(secret, "abcdef") is None


def test_verify_rejects_code_from_other_secret(frozen_time):
    secret = generate_totp_secret()
    other = generate_totp_secret()
    assert verify_totp_code(secret, _code_for_step_offset(other, 0)) is None


# ── verify_totp_code: replay rejection (GHSA-xqfh-2j9p-vmff) ───────────────


def test_verify_rejects_replay_of_consumed_step(frozen_time):
    """A code whose matched step equals the last consumed step is a replay."""
    secret = generate_totp_secret()
    current_step = FIXED_NOW // INTERVAL
    code = _code_for_step_offset(secret, 0)
    # First use succeeds and yields the step to persist.
    assert verify_totp_code(secret, code) == current_step
    # Presenting it again with that step recorded as last-consumed → refused.
    assert verify_totp_code(secret, code, last_timestep=current_step) is None


def test_verify_accepts_fresh_step_after_older_consumed(frozen_time):
    """last_timestep is the previous step: the current code is strictly newer
    and must be accepted (the <= comparison is exclusive of the future)."""
    secret = generate_totp_secret()
    current_step = FIXED_NOW // INTERVAL
    code = _code_for_step_offset(secret, 0)
    assert verify_totp_code(secret, code, last_timestep=current_step - 1) == current_step


def test_verify_rejects_stale_window_code_after_consumption(frozen_time):
    """The <= (not ==) guard also blocks replaying *last* window's code via
    the drift tolerance once the current step has been consumed: the previous
    step (current-1) is <= last_timestep (current)."""
    secret = generate_totp_secret()
    current_step = FIXED_NOW // INTERVAL
    prev_code = _code_for_step_offset(secret, -1)
    # Current step already consumed → last_timestep = current_step.
    assert verify_totp_code(secret, prev_code, last_timestep=current_step) is None


def test_verify_no_last_timestep_skips_replay_check(frozen_time):
    """When no step has ever been consumed (last_timestep=None), a valid code
    is accepted — the replay gate only engages once a step is recorded."""
    secret = generate_totp_secret()
    assert verify_totp_code(secret, _code_for_step_offset(secret, 0), last_timestep=None) is not None
