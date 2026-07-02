"""GHSA-6j38-7gfm-ch45 — SMTP TLS context builder regressions.

The pre-fix ``smtplib.SMTP_SSL(...)`` / ``server.starttls()`` calls
omitted the ``context=`` argument entirely, so smtplib fell back to
``ssl._create_stdlib_context()`` which sets ``verify_mode=CERT_NONE``
and ``check_hostname=False``. Every outbound mail — including the
unauthenticated password-reset token — travelled through a TLS
handshake that accepted any certificate.

The fix builds a verifying SSL context from settings (mirroring the
LDAP TLS pattern in `auth/ldap_auth.py`) and passes it explicitly.
This module pins the context-builder's contract: strict-by-default,
optional CA cert override, opt-out via `smtp_tls_verify=false` with
a WARNING log.
"""

from __future__ import annotations

import logging
import ssl

import pytest

from utils.email_service import _build_smtp_tls_context


class TestDefaultVerifying:
    """Zero settings → strict verify. The whole point of the fix."""

    def test_no_settings_yields_verifying_context(self):
        ctx = _build_smtp_tls_context({})
        assert ctx.verify_mode == ssl.CERT_REQUIRED
        assert ctx.check_hostname is True

    def test_verify_true_string_yields_verifying_context(self):
        ctx = _build_smtp_tls_context({"smtp_tls_verify": "true"})
        assert ctx.verify_mode == ssl.CERT_REQUIRED
        assert ctx.check_hostname is True

    def test_unknown_value_treated_as_default_verify(self):
        # Anything not the literal string "false" (case-insensitive)
        # falls through to verify — matches the LDAP pattern and
        # errs on the side of security.
        ctx = _build_smtp_tls_context({"smtp_tls_verify": "yes"})
        assert ctx.verify_mode == ssl.CERT_REQUIRED


class TestDisableVerify:
    """The last-resort opt-out for on-prem operators."""

    def test_verify_false_disables_check(self):
        ctx = _build_smtp_tls_context({"smtp_tls_verify": "false"})
        assert ctx.verify_mode == ssl.CERT_NONE
        assert ctx.check_hostname is False

    def test_verify_false_case_insensitive(self):
        ctx = _build_smtp_tls_context({"smtp_tls_verify": "FALSE"})
        assert ctx.verify_mode == ssl.CERT_NONE

    def test_verify_false_emits_warning(self, caplog):
        # Pin the log signal — this is the only telemetry an operator
        # gets that they've deliberately relaxed the check.
        with caplog.at_level(logging.WARNING, logger="utils.email_service"):
            _build_smtp_tls_context({"smtp_tls_verify": "false"})
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert any("DISABLED" in r.message for r in warnings)


class TestCustomCA:
    """Private-CA path: the operator supplies a PEM in settings, we
    load it into a verifying context. Uses a self-signed cert
    generated on the fly rather than a fixture PEM (keeps the test
    self-contained + doesn't ship a real cert)."""

    def _make_selfsigned(self) -> str:
        """Generate a self-signed cert PEM in memory."""
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
        from datetime import datetime, timedelta

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "6j38-test-ca"),
        ])
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.utcnow())
            .not_valid_after(datetime.utcnow() + timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(key, hashes.SHA256())
        )
        return cert.public_bytes(serialization.Encoding.PEM).decode()

    def test_ca_cert_loads(self):
        # A verifying context loaded with a specific CA still has
        # CERT_REQUIRED + check_hostname; only its trust store changes.
        pem = self._make_selfsigned()
        ctx = _build_smtp_tls_context({"smtp_tls_ca_cert": pem})
        assert ctx.verify_mode == ssl.CERT_REQUIRED
        assert ctx.check_hostname is True

    def test_ca_cert_overrides_verify_setting(self):
        # If the operator supplies a CA cert we assume they want to
        # verify — the presence of the cert is the signal, not a
        # separate flag.
        pem = self._make_selfsigned()
        ctx = _build_smtp_tls_context({
            "smtp_tls_ca_cert": pem,
            "smtp_tls_verify": "false",  # should be ignored when CA present
        })
        assert ctx.verify_mode == ssl.CERT_REQUIRED

    def test_malformed_ca_cert_raises(self):
        # Garbage in the CA cert setting is a config error — surface it
        # rather than silently ignoring and falling back to defaults.
        with pytest.raises(Exception):
            _build_smtp_tls_context({"smtp_tls_ca_cert": "-----BEGIN NOT A CERT-----"})

    def test_empty_ca_cert_string_falls_through(self):
        # Empty string is treated as "no override" (same shape as an
        # unset setting) — otherwise the default admin UI would need to
        # emit None vs "" for the same "not configured" state.
        ctx = _build_smtp_tls_context({"smtp_tls_ca_cert": ""})
        assert ctx.verify_mode == ssl.CERT_REQUIRED


class TestContractInvariants:
    """Whatever branch we take, the returned context must be usable —
    downstream `smtplib` treats `None` and objects that aren't
    SSLContext as errors."""

    def test_returns_sslcontext_instance(self):
        assert isinstance(_build_smtp_tls_context({}), ssl.SSLContext)

    def test_returns_sslcontext_on_disable(self):
        assert isinstance(_build_smtp_tls_context({"smtp_tls_verify": "false"}), ssl.SSLContext)
