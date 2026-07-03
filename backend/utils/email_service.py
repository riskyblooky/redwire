"""
Email service utility — sends emails via SMTP using settings from auth_settings table.
"""
import re
import smtplib
import ssl
import tempfile
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.auth_settings import AuthSetting

logger = logging.getLogger(__name__)

# GHSA-m28w-p732-3rm5 follow-up: defense-in-depth header-injection guard at
# the send_email boundary. The main GHSA already HTML-escaped user data
# rendered into the email BODY; this catches the shape where a future
# caller wires user-supplied text into the SUBJECT or RECIPIENT fields
# (e.g. an automation rule that stuffs a finding title into the subject).
# A raw ``\r\n`` in either becomes a header split — attacker smuggles
# ``\r\nBcc: attacker@evil`` and the outer stack routes a copy.
#
# Python's ``email.message`` refuses some of these at serialize time, but
# ``smtplib.SMTP.sendmail(msg.as_string())`` will happily hand off a
# pre-serialized string that already contains the injection. Fail loudly
# at the wrapper instead of trusting library-layer behavior.
_HEADER_INJECTION_RE = re.compile(r"[\r\n]")

# Loose but strict-enough: no whitespace or comma (RFC-compliant addresses
# never contain either outside of quoted-local-parts, which we're not
# handling), single ``@``, at least one dot in the domain. `email.utils
# .parseaddr` is more permissive and returns a tuple even for garbage
# input, so we do the reject upstream of it.
_ADDR_RE = re.compile(r"^[^\s,<>]+@[^\s,<>]+\.[^\s,<>]+$")


def _guard_email_headers(subject: str, recipients) -> None:
    """Reject subject values or recipient addresses that could inject
    into the SMTP header stream. Raises ValueError on bad input so the
    caller — typically an automation action — surfaces the failure in
    logs and fails the action rather than silently sending elsewhere."""
    if _HEADER_INJECTION_RE.search(subject or ""):
        raise ValueError("Email subject contains CR/LF; refusing to send.")
    if isinstance(recipients, str):
        recipients = [recipients]
    for r in recipients or ():
        if not isinstance(r, str) or _HEADER_INJECTION_RE.search(r):
            raise ValueError(f"Recipient address contains CR/LF: {r!r}")
        if not _ADDR_RE.match(r):
            raise ValueError(f"Recipient address is not RFC-compliant: {r!r}")


async def _get_smtp_settings(db: AsyncSession) -> Dict[str, str]:
    """Load SMTP settings from the auth_settings table."""
    result = await db.execute(
        select(AuthSetting).where(AuthSetting.key.like("smtp_%"))
    )
    return {s.key: s.value or "" for s in result.scalars().all()}


def _build_smtp_tls_context(settings: Dict[str, str]) -> ssl.SSLContext:
    """GHSA-6j38-7gfm-ch45: build a verifying SSL context for SMTP.

    Mirrors the LDAP TLS pattern in ``auth.ldap_auth._build_tls_config``:
    strict-by-default with two operator opt-ins for on-prem setups whose
    SMTP relay isn't backed by a public CA.

      - ``smtp_tls_ca_cert`` (PEM text): loaded into the context so a
        private-CA-issued cert is verified against the operator-supplied
        chain rather than the system bundle. Written to a temp file
        because ``load_verify_locations`` doesn't accept in-memory PEM
        on older Pythons; unlinked after loading.
      - ``smtp_tls_verify=false``: last-resort disable. Emits a WARNING
        so the operator sees the state in logs and monitoring.

    Absent both settings: ``ssl.create_default_context()`` — the
    system CA bundle, ``CERT_REQUIRED``, ``check_hostname=True``. That
    reverses the pre-fix behaviour where ``smtplib`` silently fell
    back to ``_create_stdlib_context()`` (``CERT_NONE``) whenever
    ``context=`` was omitted — the actual defect the CVE names.
    """
    ca_cert_pem = settings.get("smtp_tls_ca_cert", "").strip()
    tls_verify = settings.get("smtp_tls_verify", "true").lower() != "false"

    if ca_cert_pem:
        ctx = ssl.create_default_context()
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pem", mode="w")
        try:
            tmp.write(ca_cert_pem)
            tmp.close()
            ctx.load_verify_locations(cafile=tmp.name)
        finally:
            try:
                import os as _os
                _os.unlink(tmp.name)
            except OSError:
                pass
        return ctx

    if not tls_verify:
        logger.warning(
            "SMTP TLS certificate validation is DISABLED "
            "(smtp_tls_verify=false). Outbound mail can be intercepted."
        )
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    return ssl.create_default_context()


def _send_smtp(
    host: str,
    port: int,
    username: str,
    password: str,
    use_tls: bool,
    from_email: str,
    from_name: str,
    to_email: str,
    subject: str,
    html_body: str,
    text_body: Optional[str] = None,
    tls_context: Optional[ssl.SSLContext] = None,
) -> bool:
    """Low-level SMTP send.  Returns True on success."""
    msg = MIMEMultipart("alternative")
    msg["From"] = f"{from_name} <{from_email}>" if from_name else from_email
    msg["To"] = to_email
    msg["Subject"] = subject

    if text_body:
        msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    # GHSA-6j38-7gfm-ch45: fall back to a verifying default context if the
    # caller didn't supply one — treat "no context passed" as "verify
    # against the system CA bundle", never as "accept any cert" which is
    # what smtplib does when context= is omitted entirely.
    if tls_context is None:
        tls_context = ssl.create_default_context()

    try:
        if use_tls and port == 465:
            # Implicit TLS (SMTPS)
            server = smtplib.SMTP_SSL(host, port, timeout=15, context=tls_context)
        else:
            server = smtplib.SMTP(host, port, timeout=15)
            if use_tls:
                server.starttls(context=tls_context)

        if username and password:
            server.login(username, password)

        server.sendmail(from_email, [to_email], msg.as_string())
        server.quit()
        logger.info(f"Email sent to {to_email}: {subject}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        raise


async def send_email(
    db: AsyncSession,
    to_email: str,
    subject: str,
    html_body: str,
    text_body: Optional[str] = None,
) -> bool:
    """Send an email using SMTP settings from the database."""
    # Header/recipient guard — see _guard_email_headers docstring. Run
    # BEFORE loading settings so a bad caller fails fast without touching
    # the DB. GHSA-m28w-p732-3rm5 follow-up.
    _guard_email_headers(subject, to_email)

    cfg = await _get_smtp_settings(db)

    if cfg.get("smtp_enabled", "false").lower() != "true":
        logger.warning("Email not sent — SMTP is disabled")
        return False

    host = cfg.get("smtp_host", "")
    port = int(cfg.get("smtp_port", "587"))
    username = cfg.get("smtp_username", "")
    password = cfg.get("smtp_password", "")
    use_tls = cfg.get("smtp_use_tls", "true").lower() == "true"
    from_email = cfg.get("smtp_from_email", "")
    from_name = cfg.get("smtp_from_name", "RedWire")

    if not host or not from_email:
        logger.error("SMTP host or from_email not configured")
        return False

    tls_context = _build_smtp_tls_context(cfg) if use_tls else None

    return _send_smtp(
        host=host,
        port=port,
        username=username,
        tls_context=tls_context,
        password=password,
        use_tls=use_tls,
        from_email=from_email,
        from_name=from_name,
        to_email=to_email,
        subject=subject,
        html_body=html_body,
        text_body=text_body,
    )


async def send_password_reset_email(
    db: AsyncSession,
    to_email: str,
    reset_url: str,
    username: str,
) -> bool:
    """Send a password reset email."""
    import os
    html = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 480px; margin: 0 auto; padding: 32px; background: #0a0f1a; color: #e2e8f0; border-radius: 12px;">
        <div style="text-align: center; margin-bottom: 24px;">
            <h1 style="color: #ef4444; font-size: 20px; margin: 0;">🔐 RedWire</h1>
            <p style="color: #94a3b8; font-size: 12px; margin-top: 4px;">Password Reset Request</p>
        </div>
        <p style="font-size: 14px; line-height: 1.6;">Hi <strong>{username}</strong>,</p>
        <p style="font-size: 14px; line-height: 1.6; color: #94a3b8;">
            A password reset was requested for your account. Click the button below to set a new password.
            This link expires in <strong>30 minutes</strong>.
        </p>
        <div style="text-align: center; margin: 28px 0;">
            <a href="{reset_url}"
               style="display: inline-block; padding: 12px 32px; background: #dc2626; color: white; text-decoration: none;
                      font-weight: 600; font-size: 14px; border-radius: 8px;">
                Reset Password
            </a>
        </div>
        <p style="font-size: 12px; color: #64748b; line-height: 1.5;">
            If you didn't request this, you can safely ignore this email. Your password won't be changed.
        </p>
        <hr style="border: none; border-top: 1px solid #1e293b; margin: 24px 0;" />
        <p style="font-size: 11px; color: #475569; text-align: center;">
            RedWire Security Platform
        </p>
    </div>
    """
    text = f"Hi {username},\n\nReset your password: {reset_url}\n\nThis link expires in 30 minutes.\n\nIf you didn't request this, ignore this email."

    return await send_email(db, to_email, "RedWire — Password Reset", html, text)


async def send_test_email(db: AsyncSession, to_email: str) -> bool:
    """Send a test email to verify SMTP configuration."""
    html = """
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 480px; margin: 0 auto; padding: 32px; background: #0a0f1a; color: #e2e8f0; border-radius: 12px;">
        <div style="text-align: center; margin-bottom: 24px;">
            <h1 style="color: #ef4444; font-size: 20px; margin: 0;">✅ RedWire</h1>
            <p style="color: #94a3b8; font-size: 12px; margin-top: 4px;">Email Configuration Test</p>
        </div>
        <p style="font-size: 14px; line-height: 1.6; text-align: center;">
            Your SMTP email configuration is working correctly!
        </p>
        <hr style="border: none; border-top: 1px solid #1e293b; margin: 24px 0;" />
        <p style="font-size: 11px; color: #475569; text-align: center;">
            RedWire Security Platform
        </p>
    </div>
    """
    return await send_email(db, to_email, "RedWire — SMTP Test Successful", html)
