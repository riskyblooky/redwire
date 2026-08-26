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
from email.mime.image import MIMEImage
from pathlib import Path

# Bundled logo, embedded inline (CID) in branded emails so it renders without
# depending on a reachable image URL. Referenced as <img src="cid:redwire-logo">.
LOGO_CID = "redwire-logo"
_LOGO_PATH = Path(__file__).resolve().parent.parent / "assets" / "redwire.png"
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
    # If the HTML references the inline logo, wrap the alternative part in a
    # multipart/related so the CID image resolves; otherwise keep it simple.
    embed_logo = (f"cid:{LOGO_CID}" in (html_body or "")) and _LOGO_PATH.exists()

    alt = MIMEMultipart("alternative")
    if text_body:
        alt.attach(MIMEText(text_body, "plain"))
    alt.attach(MIMEText(html_body, "html"))

    if embed_logo:
        msg = MIMEMultipart("related")
        msg.attach(alt)
        try:
            with open(_LOGO_PATH, "rb") as fh:
                img = MIMEImage(fh.read(), _subtype="png")
            img.add_header("Content-ID", f"<{LOGO_CID}>")
            img.add_header("Content-Disposition", "inline", filename="redwire.png")
            msg.attach(img)
        except Exception as e:
            logger.warning(f"Could not embed email logo: {e}")
            msg = alt  # fall back to the alternative part; alt text covers it
    else:
        msg = alt

    msg["From"] = f"{from_name} <{from_email}>" if from_name else from_email
    msg["To"] = to_email
    msg["Subject"] = subject

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


async def send_password_changed_email(
    db: AsyncSession,
    to_email: str,
    username: str,
) -> bool:
    """Security notice sent AFTER a password reset completes — so a victim whose
    account was reset by an attacker finds out and can act."""
    import html as _html
    safe_user = _html.escape(username or "")
    html = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 480px; margin: 0 auto; padding: 32px; background: #0a0f1a; color: #e2e8f0; border-radius: 12px;">
        <div style="text-align: center; margin-bottom: 24px;">
            <h1 style="color: #ef4444; font-size: 20px; margin: 0;">🔒 RedWire</h1>
            <p style="color: #94a3b8; font-size: 12px; margin-top: 4px;">Password Changed</p>
        </div>
        <p style="font-size: 14px; line-height: 1.6;">Hi <strong>{safe_user}</strong>,</p>
        <p style="font-size: 14px; line-height: 1.6; color: #94a3b8;">
            Your RedWire account password was just changed, and all active sessions were signed out.
        </p>
        <div style="margin: 24px 0; padding: 12px 16px; background: rgba(239,68,68,0.08); border: 1px solid rgba(239,68,68,0.25); border-radius: 8px;">
            <p style="font-size: 13px; line-height: 1.5; color: #fca5a5; margin: 0;">
                If you did <strong>not</strong> make this change, your account may be compromised —
                contact your administrator immediately.
            </p>
        </div>
        <p style="font-size: 12px; color: #64748b; line-height: 1.5;">
            If this was you, no further action is needed.
        </p>
        <hr style="border: none; border-top: 1px solid #1e293b; margin: 24px 0;" />
        <p style="font-size: 11px; color: #475569; text-align: center;">
            RedWire Security Platform
        </p>
    </div>
    """
    text = (
        f"Hi {username},\n\nYour RedWire account password was just changed and all active "
        f"sessions were signed out.\n\nIf you did NOT make this change, your account may be "
        f"compromised — contact your administrator immediately.\n\nIf this was you, no action is needed."
    )
    return await send_email(db, to_email, "RedWire — Your password was changed", html, text)


async def send_test_email(db: AsyncSession, to_email: str) -> bool:
    """Send a test email to verify SMTP configuration.

    Routed through the shared branded notification template so this doubles as a
    live preview of exactly what notification / automation emails look like
    (logo, dark theme, button, dark-mode behaviour) in the admin's real client.
    """
    html, text = render_notification_email(
        heading="SMTP Test",
        title="Your email configuration is working",
        message=(
            "This is a test message from RedWire. If you can read this, your SMTP "
            "settings are correct and notification emails will be delivered.\n\n"
            "This is also a preview of the notification email template — the same "
            "layout is used for per-user notifications and automation email actions."
        ),
        meta=[("Delivered to", to_email)],
    )
    return await send_email(db, to_email, "RedWire — SMTP Test Successful", html, text)


def render_notification_email(
    heading: str,
    title: str,
    message: Optional[str] = None,
    link: Optional[str] = None,
    link_label: str = "Open in RedWire",
    meta: Optional[list] = None,
) -> tuple:
    """Build a dark-themed HTML + plaintext body for a notification-style email.

    This is the shared "nice email" renderer — used for per-user notification
    emails and for automation email actions, so both land as a styled card
    instead of a raw ``<pre>`` JSON dump. Every caller-supplied string is
    HTML-escaped into the HTML part, so finding titles / note names / automation
    details are all safe to pass through verbatim. ``meta`` is an optional list
    of ``(label, value)`` rows rendered as a small key/value table.

    Returns ``(html_body, text_body)``.
    """
    import html as _html

    def esc(s):
        return _html.escape(str(s)) if s is not None else ""

    # Brand palette (mirrors the app's dark theme + RedWire red accent).
    BG = "#060608"          # page background
    CARD = "#0c0c12"        # card surface
    BORDER = "#1e1e2a"      # hairlines
    ACCENT = "#dc2626"      # RedWire brand red (matches the logo)
    ACCENT_SOFT = "rgba(220,38,38,0.14)"
    EYEBROW = "#fca5a5"     # readable red-tint for the header eyebrow label
    TEXT = "#e2e8f0"
    MUTED = "#94a3b8"
    FAINT = "#64748b"

    meta_html = ""
    meta_text_lines = []
    if meta:
        rows = ""
        for label, value in meta:
            if value is None or value == "":
                continue
            rows += (
                "<tr>"
                f"<td style='padding:6px 14px 6px 0;color:{FAINT};font-size:12px;white-space:nowrap;vertical-align:top;'>{esc(label)}</td>"
                f"<td style='padding:6px 0;color:#cbd5e1;font-size:12px;line-height:1.5;'>{esc(value)}</td>"
                "</tr>"
            )
            meta_text_lines.append(f"{label}: {value}")
        if rows:
            meta_html = (
                f"<table role='presentation' bgcolor='{BG}' cellpadding='0' cellspacing='0' border='0' "
                f"style='width:100%;margin:16px 0 4px;border-collapse:collapse;background-color:{BG};"
                f"border:1px solid {BORDER};border-radius:10px;'>"
                f"<tr><td style='padding:8px 14px;'><table role='presentation' cellpadding='0' cellspacing='0' border='0'>{rows}</table></td></tr>"
                f"</table>"
            )

    message_html = (
        f"<p style='font-size:14px;line-height:1.65;color:#cbd5e1;margin:14px 0 0;white-space:pre-wrap;'>{esc(message)}</p>"
        if message else ""
    )

    # Bulletproof centered button. Outlook on Windows repaints CSS/bgcolor
    # buttons in dark mode (the accent drifts toward blue and the label darkens),
    # so we hand Outlook a VML <roundrect> whose fillcolor + label colour are
    # locked against that transform. Every other client gets the CSS button.
    button_html = ""
    if link:
        safe_link = esc(link)
        label = f"{esc(link_label)} &rarr;"
        button_html = (
            f"<table role='presentation' cellpadding='0' cellspacing='0' border='0' style='margin:26px 0 6px;'>"
            f"<tr><td align='center'>"
            f"<!--[if mso]>"
            f"<v:roundrect xmlns:v='urn:schemas-microsoft-com:vml' xmlns:w='urn:schemas-microsoft-com:office:word' "
            f"href='{safe_link}' style='height:42px;v-text-anchor:middle;width:240px;' arcsize='19%' stroke='f' fillcolor='{ACCENT}'>"
            f"<w:anchorlock/>"
            f"<center style='color:#ffffff;font-family:Segoe UI,Arial,sans-serif;font-size:13px;font-weight:600;'>{label}</center>"
            f"</v:roundrect>"
            f"<![endif]-->"
            f"<!--[if !mso]><!-- -->"
            f"<table role='presentation' cellpadding='0' cellspacing='0' border='0'>"
            f"<tr><td align='center' bgcolor='{ACCENT}' style='background-color:{ACCENT};border-radius:8px;padding:12px 30px;'>"
            f"<a href='{safe_link}' target='_blank' style='font-family:-apple-system,BlinkMacSystemFont,\"Segoe UI\",Roboto,Helvetica,Arial,sans-serif;"
            f"font-size:13px;font-weight:600;color:#ffffff;text-decoration:none;'>{label}</a>"
            f"</td></tr></table>"
            f"<!--<![endif]-->"
            f"</td></tr></table>"
        )

    # Logo embedded inline (CID). The wordmark sits alongside as bulletproof
    # alt text so the brand still reads if a client suppresses images.
    brand_mark = (
        f"<img src='cid:{LOGO_CID}' width='120' alt='RedWire' "
        f"style='display:block;height:auto;border:0;outline:none;text-decoration:none;-ms-interpolation-mode:bicubic;' />"
    )

    preheader = esc(title)

    html = f"""\
<!DOCTYPE html>
<html lang="en" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<!-- Tell dark-mode-aware clients (Apple Mail, iOS, Outlook.com) this email is
     already dark-designed, so they DON'T auto-invert it into an unreadable
     light-on-light mess. -->
<meta name="color-scheme" content="dark" />
<meta name="supported-color-schemes" content="dark" />
<title>RedWire</title>
<style>
  :root {{ color-scheme: dark; supported-color-schemes: dark; }}
  body {{ color-scheme: dark; }}
  /* Re-assert the dark surfaces where a client still tries to recolour them. */
  @media (prefers-color-scheme: dark) {{
    .rw-bg {{ background-color: {BG} !important; }}
    .rw-card {{ background-color: {CARD} !important; }}
  }}
  /* Outlook.com dark mode rewrites colours behind [data-ogsc]/[data-ogsb]. */
  [data-ogsb] .rw-bg {{ background-color: {BG} !important; }}
  [data-ogsb] .rw-card {{ background-color: {CARD} !important; }}
</style>
</head>
<body class="rw-bg" bgcolor="{BG}" style="margin:0;padding:0;background-color:{BG};color-scheme:dark;">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:{BG};font-size:1px;line-height:1px;">{preheader}</div>
<table role="presentation" class="rw-bg" bgcolor="{BG}" cellpadding="0" cellspacing="0" border="0" width="100%" style="background-color:{BG};padding:32px 16px;">
  <tr>
    <td align="center">
      <table role="presentation" class="rw-card" bgcolor="{CARD}" cellpadding="0" cellspacing="0" border="0" width="560" style="width:560px;max-width:100%;background-color:{CARD};border:1px solid {BORDER};border-radius:16px;overflow:hidden;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
        <!-- Header -->
        <tr>
          <td style="padding:24px 32px 20px;border-bottom:1px solid {BORDER};">
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
              <tr>
                <td align="left" style="vertical-align:middle;">{brand_mark}</td>
                <td align="right" style="vertical-align:middle;">
                  <span style="display:inline-block;padding:5px 12px;background:{ACCENT_SOFT};color:{EYEBROW};font-size:11px;font-weight:600;letter-spacing:0.04em;text-transform:uppercase;border-radius:999px;">{esc(heading)}</span>
                </td>
              </tr>
            </table>
          </td>
        </tr>
        <!-- Accent rule -->
        <tr><td bgcolor="{ACCENT}" style="height:3px;background-color:{ACCENT};line-height:3px;font-size:0;">&nbsp;</td></tr>
        <!-- Body -->
        <tr>
          <td style="padding:28px 32px 8px;">
            <h1 style="margin:0;font-size:18px;font-weight:700;color:{TEXT};line-height:1.4;">{esc(title)}</h1>
            {message_html}
            {meta_html}
            {button_html}
          </td>
        </tr>
        <!-- Footer -->
        <tr>
          <td style="padding:20px 32px 26px;border-top:1px solid {BORDER};">
            <p style="margin:0;font-size:11px;line-height:1.6;color:{FAINT};">
              You're receiving this because email notifications are enabled for this event in your RedWire profile.
              Manage them under <span style="color:{MUTED};">Profile &rarr; Notifications</span>.
            </p>
            <p style="margin:10px 0 0;font-size:11px;color:#3f3f52;">RedWire &middot; Red Team Operations Platform</p>
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>
</body>
</html>"""

    text_parts = [f"RedWire — {heading}", "", title]
    if message:
        text_parts += ["", str(message)]
    if meta_text_lines:
        text_parts += [""] + meta_text_lines
    if link:
        text_parts += ["", f"{link_label}: {link}"]
    text = "\n".join(text_parts)
    return html, text


async def send_notification_email(
    db: AsyncSession,
    to_email: str,
    subject: str,
    title: str,
    message: Optional[str] = None,
    link: Optional[str] = None,
    heading: str = "Notification",
    link_label: str = "Open in RedWire",
    meta: Optional[list] = None,
) -> bool:
    """Render and send a styled notification email. Subject is stripped of
    CR/LF so a resource name spliced into it can't trip the header guard."""
    subject = (subject or "RedWire Notification").replace("\r", " ").replace("\n", " ")
    html, text = render_notification_email(
        heading=heading, title=title, message=message,
        link=link, link_label=link_label, meta=meta,
    )
    return await send_email(db, to_email, subject, html, text)
