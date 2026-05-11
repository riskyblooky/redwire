"""
Email service utility — sends emails via SMTP using settings from auth_settings table.
"""
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.auth_settings import AuthSetting

logger = logging.getLogger(__name__)


async def _get_smtp_settings(db: AsyncSession) -> Dict[str, str]:
    """Load SMTP settings from the auth_settings table."""
    result = await db.execute(
        select(AuthSetting).where(AuthSetting.key.like("smtp_%"))
    )
    return {s.key: s.value or "" for s in result.scalars().all()}


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
) -> bool:
    """Low-level SMTP send.  Returns True on success."""
    msg = MIMEMultipart("alternative")
    msg["From"] = f"{from_name} <{from_email}>" if from_name else from_email
    msg["To"] = to_email
    msg["Subject"] = subject

    if text_body:
        msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        if use_tls and port == 465:
            # Implicit TLS (SMTPS)
            server = smtplib.SMTP_SSL(host, port, timeout=15)
        else:
            server = smtplib.SMTP(host, port, timeout=15)
            if use_tls:
                server.starttls()

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

    return _send_smtp(
        host=host,
        port=port,
        username=username,
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
