"""
TOTP (Time-based One-Time Password) utilities for two-factor authentication.

Uses pyotp (RFC 6238) — compatible with Google Authenticator, Duo Mobile, Authy,
Microsoft Authenticator, and any standard TOTP app.
"""

import time
from typing import Optional

import pyotp
import qrcode
import io
import base64


ISSUER_NAME = "RedWire"


def generate_totp_secret() -> str:
    """Generate a new random base32-encoded TOTP secret."""
    return pyotp.random_base32()


def get_totp_uri(secret: str, username: str) -> str:
    """Build an otpauth:// provisioning URI for QR code scanning."""
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=username, issuer_name=ISSUER_NAME)


def generate_qr_base64(uri: str) -> str:
    """Generate a QR code as a base64-encoded PNG data URI."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=6,
        border=2,
    )
    qr.add_data(uri)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{b64}"


def verify_totp_code(
    secret: str,
    code: str,
    last_timestep: Optional[int] = None,
) -> Optional[int]:
    """Verify a 6-digit TOTP code against the secret.

    Allows ±1 time-step window (30 seconds each direction) to account for
    slight clock drift between server and authenticator app.

    Returns the matched time-step (int) on success, or None on failure
    (invalid code, or matched step <= last_timestep — a replay).
    GHSA-xqfh-2j9p-vmff.

    Callers are expected to persist the returned step into
    ``user.totp_last_timestep`` in the same transaction so the next call
    sees the consumed step. The ``<=`` comparison (rather than ``==``)
    also blocks an attacker from presenting last window's code via the
    valid_window drift tolerance after the current step has been used.
    """
    totp = pyotp.TOTP(secret)
    now = int(time.time())
    current_step = now // totp.interval
    for offset in (0, -1, 1):
        if totp.at(now, counter_offset=offset) == code:
            step = current_step + offset
            if last_timestep is not None and step <= last_timestep:
                return None
            return step
    return None
