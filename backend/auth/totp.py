"""
TOTP (Time-based One-Time Password) utilities for two-factor authentication.

Uses pyotp (RFC 6238) — compatible with Google Authenticator, Duo Mobile, Authy,
Microsoft Authenticator, and any standard TOTP app.
"""

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


def verify_totp_code(secret: str, code: str) -> bool:
    """
    Verify a 6-digit TOTP code against the secret.

    Allows ±1 time-step window (30 seconds each direction) to account
    for slight clock drift between server and authenticator app.
    """
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)
