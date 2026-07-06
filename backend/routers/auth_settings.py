"""
Admin authentication settings router.
Manages LDAP and SAML SSO configuration stored in the auth_settings table.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Dict

from database import get_db
from models.user import User, UserRole
from models.auth_settings import AuthSetting
from schemas.auth_settings import (
    LdapSettings, SamlSettings, AuthSettingsResponse,
    LdapTestRequest, AuthProvidersResponse,
    SmtpSettings, SmtpTestRequest,
)
from auth.dependencies import get_current_user, require_roles, ADMIN_ROLES, WRITE_ADMIN_ROLES
from auth.ldap_auth import test_ldap_connection

router = APIRouter(prefix="/admin/auth-settings", tags=["admin-auth-settings"])

# Keys grouped by provider. ``ldap_tls_enabled`` is retained in the list
# for read-side back-compat: old installs may still have the row, and the
# GET handler falls back to it when ``ldap_tls_mode`` is absent. Writes
# only set the new keys.
LDAP_KEYS = [
    "ldap_enabled", "ldap_server_url", "ldap_bind_dn", "ldap_bind_password",
    "ldap_search_base", "ldap_search_filter", "ldap_username_attribute",
    "ldap_email_attribute", "ldap_fullname_attribute",
    "ldap_tls_mode", "ldap_tls_verify", "ldap_tls_enabled",
    "ldap_tls_ca_cert",
    "ldap_debug_enabled",
]
SAML_KEYS = [
    "saml_enabled", "saml_idp_entity_id", "saml_idp_sso_url", "saml_idp_slo_url",
    "saml_idp_x509_cert", "saml_sp_entity_id", "saml_want_messages_signed",
]
SMTP_KEYS = [
    "smtp_enabled", "smtp_host", "smtp_port", "smtp_username", "smtp_password",
    "smtp_from_email", "smtp_from_name", "smtp_use_tls",
]
ENCRYPTED_KEYS = {"ldap_bind_password", "saml_idp_x509_cert", "ldap_tls_ca_cert", "smtp_password"}


async def _get_all_settings(db: AsyncSession) -> Dict[str, str]:
    """Load all auth_settings from DB into a dict."""
    result = await db.execute(select(AuthSetting))
    return {s.key: s.value or "" for s in result.scalars().all()}


async def _set_setting(db: AsyncSession, key: str, value: str, user_id: str):
    """Upsert a single setting."""
    result = await db.execute(select(AuthSetting).where(AuthSetting.key == key))
    setting = result.scalar_one_or_none()
    if setting:
        setting.value = value
        setting.updated_by = user_id
    else:
        setting = AuthSetting(
            key=key,
            value=value,
            is_encrypted=key in ENCRYPTED_KEYS,
            updated_by=user_id,
        )
        db.add(setting)


def _mask(value: str) -> str:
    """Mask sensitive values for API responses."""
    if not value:
        return ""
    if len(value) <= 8:
        return "••••••••"
    return value[:4] + "••••" + value[-4:]


@router.get(
    "",
    response_model=AuthSettingsResponse,
    summary="Get authentication settings",
    description="Returns all LDAP and SAML SSO configuration. Sensitive values (passwords, certificates) are masked.",
)
async def get_auth_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(ADMIN_ROLES)),
):
    """Get all authentication settings (passwords masked)."""
    raw = await _get_all_settings(db)

    # tls_mode: prefer the new field. If it's absent, migrate from the
    # legacy ``ldap_tls_enabled`` bool so the UI still shows a sensible
    # value on first load after upgrade. See _resolve_tls_mode in
    # auth/ldap_auth.py for the mirrored logic on the runtime path.
    tls_mode_raw = (raw.get("ldap_tls_mode") or "").strip().lower()
    if tls_mode_raw not in ("none", "ldaps", "starttls"):
        legacy_enabled = raw.get("ldap_tls_enabled", "true").lower() == "true"
        tls_mode_raw = "ldaps" if legacy_enabled else "none"

    ldap = LdapSettings(
        enabled=raw.get("ldap_enabled", "false").lower() == "true",
        server_url=raw.get("ldap_server_url", ""),
        bind_dn=raw.get("ldap_bind_dn", ""),
        bind_password=_mask(raw.get("ldap_bind_password", "")),
        search_base=raw.get("ldap_search_base", ""),
        search_filter=raw.get("ldap_search_filter", "(uid={username})"),
        username_attribute=raw.get("ldap_username_attribute", "uid"),
        email_attribute=raw.get("ldap_email_attribute", "mail"),
        fullname_attribute=raw.get("ldap_fullname_attribute", "cn"),
        tls_mode=tls_mode_raw,
        tls_verify=raw.get("ldap_tls_verify", "true").lower() != "false",
        tls_ca_cert=_mask(raw.get("ldap_tls_ca_cert", "")),
        debug_enabled=raw.get("ldap_debug_enabled", "false").lower() == "true",
    )

    saml = SamlSettings(
        enabled=raw.get("saml_enabled", "false").lower() == "true",
        idp_entity_id=raw.get("saml_idp_entity_id", ""),
        idp_sso_url=raw.get("saml_idp_sso_url", ""),
        idp_slo_url=raw.get("saml_idp_slo_url", ""),
        idp_x509_cert=_mask(raw.get("saml_idp_x509_cert", "")),
        sp_entity_id=raw.get("saml_sp_entity_id", ""),
        want_messages_signed=raw.get("saml_want_messages_signed", "false").lower() == "true",
    )

    return AuthSettingsResponse(ldap=ldap, saml=saml)


@router.put(
    "/ldap",
    response_model=AuthSettingsResponse,
    summary="Update LDAP settings",
    description="Updates LDAP configuration. Set bind_password to null to keep the existing value.",
)
async def update_ldap_settings(
    settings: LdapSettings,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(WRITE_ADMIN_ROLES)),
):
    """Update LDAP configuration."""
    mapping = {
        "ldap_enabled": str(settings.enabled).lower(),
        "ldap_server_url": settings.server_url,
        "ldap_bind_dn": settings.bind_dn,
        "ldap_search_base": settings.search_base,
        "ldap_search_filter": settings.search_filter,
        "ldap_username_attribute": settings.username_attribute,
        "ldap_email_attribute": settings.email_attribute,
        "ldap_fullname_attribute": settings.fullname_attribute,
        "ldap_tls_mode": settings.tls_mode,
        "ldap_tls_verify": str(settings.tls_verify).lower(),
        # Also mirror to the legacy key so any external tooling / a rollback
        # to an older backend build still lands somewhere reasonable.
        "ldap_tls_enabled": "false" if settings.tls_mode == "none" else "true",
        "ldap_debug_enabled": str(settings.debug_enabled).lower(),
    }

    # Only update password if a new value is provided (not None / not masked)
    if settings.bind_password and "••••" not in settings.bind_password:
        mapping["ldap_bind_password"] = settings.bind_password

    # Only update CA cert if a new value is provided
    if settings.tls_ca_cert and "••••" not in settings.tls_ca_cert:
        mapping["ldap_tls_ca_cert"] = settings.tls_ca_cert

    for key, value in mapping.items():
        await _set_setting(db, key, value, current_user.id)

    await db.commit()
    return await get_auth_settings(db=db, current_user=current_user)


@router.put(
    "/saml",
    response_model=AuthSettingsResponse,
    summary="Update SAML SSO settings",
    description="Updates SAML 2.0 SSO configuration. Set idp_x509_cert to null to keep the existing value.",
)
async def update_saml_settings(
    settings: SamlSettings,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(WRITE_ADMIN_ROLES)),
):
    """Update SAML SSO configuration."""
    mapping = {
        "saml_enabled": str(settings.enabled).lower(),
        "saml_idp_entity_id": settings.idp_entity_id,
        "saml_idp_sso_url": settings.idp_sso_url,
        "saml_idp_slo_url": settings.idp_slo_url,
        "saml_sp_entity_id": settings.sp_entity_id,
        "saml_want_messages_signed": str(settings.want_messages_signed).lower(),
    }

    # Only update cert if a new value is provided
    if settings.idp_x509_cert and "••••" not in settings.idp_x509_cert:
        mapping["saml_idp_x509_cert"] = settings.idp_x509_cert

    for key, value in mapping.items():
        await _set_setting(db, key, value, current_user.id)

    await db.commit()
    return await get_auth_settings(db=db, current_user=current_user)


@router.post(
    "/ldap/test",
    summary="Test LDAP connection",
    description="Attempts to bind to the configured LDAP server with a test username and password.",
)
async def test_ldap(
    test_data: LdapTestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(WRITE_ADMIN_ROLES)),
):
    """Test LDAP connection using stored settings."""
    raw = await _get_all_settings(db)
    # The ldap module reads unprefixed keys. Pass through both the new
    # ``tls_mode`` / ``tls_verify`` fields and the legacy ``tls_enabled``
    # bool so _resolve_tls_mode can fall back when the new fields aren't
    # set yet on a freshly-migrated install.
    settings_for_test = {
        "server_url": raw.get("ldap_server_url", ""),
        "bind_dn": raw.get("ldap_bind_dn", ""),
        "bind_password": raw.get("ldap_bind_password", ""),
        "search_base": raw.get("ldap_search_base", ""),
        "tls_mode": raw.get("ldap_tls_mode", ""),
        "tls_verify": raw.get("ldap_tls_verify", "true"),
        "tls_enabled": raw.get("ldap_tls_enabled", "true"),
        "tls_ca_cert": raw.get("ldap_tls_ca_cert", ""),
    }
    debug = raw.get("ldap_debug_enabled", "false").lower() == "true"
    return test_ldap_connection(settings_for_test, debug=debug)


# ─── Splash Screen / Login Banner ─────────────────────────────────────────────

from pydantic import BaseModel, Field

class SplashSettings(BaseModel):
    enabled: bool = False
    title: str = Field("", max_length=255)
    message: str = Field("", max_length=8192)

@router.get(
    "/splash",
    summary="Get splash screen settings",
    description="Returns the login splash screen / DoD banner configuration.",
)
async def get_splash_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(ADMIN_ROLES)),
):
    """Get splash screen settings (admin view)."""
    raw = await _get_all_settings(db)
    return SplashSettings(
        enabled=raw.get("splash_enabled", "false").lower() == "true",
        title=raw.get("splash_title", ""),
        message=raw.get("splash_message", ""),
    )


@router.put(
    "/splash",
    summary="Update splash screen settings",
    description="Updates the login splash screen / DoD banner configuration.",
)
async def update_splash_settings(
    settings: SplashSettings,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(WRITE_ADMIN_ROLES)),
):
    """Update splash screen settings."""
    mapping = {
        "splash_enabled": str(settings.enabled).lower(),
        "splash_title": settings.title,
        "splash_message": settings.message,
    }
    for key, value in mapping.items():
        await _set_setting(db, key, value, current_user.id)

    await db.commit()
    return SplashSettings(
        enabled=settings.enabled,
        title=settings.title,
        message=settings.message,
    )


# ── SMTP ────────────────────────────────────────────────────────────────────────

@router.get("/smtp", dependencies=[Depends(require_roles(ADMIN_ROLES))])
async def get_smtp_settings(db: AsyncSession = Depends(get_db)):
    """Return current SMTP settings (password masked)."""
    raw = await _get_all_settings(db)
    return {
        "smtp": SmtpSettings(
            enabled=raw.get("smtp_enabled", "false").lower() == "true",
            host=raw.get("smtp_host", ""),
            port=int(raw.get("smtp_port", "587")),
            username=raw.get("smtp_username", ""),
            password="••••••••" if raw.get("smtp_password") else "",
            from_email=raw.get("smtp_from_email", ""),
            from_name=raw.get("smtp_from_name", "RedWire"),
            use_tls=raw.get("smtp_use_tls", "true").lower() == "true",
        )
    }


@router.put("/smtp", dependencies=[Depends(require_roles(WRITE_ADMIN_ROLES))])
async def update_smtp_settings(
    settings: SmtpSettings,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update SMTP settings."""
    mapping = {
        "smtp_enabled": str(settings.enabled).lower(),
        "smtp_host": settings.host,
        "smtp_port": str(settings.port),
        "smtp_username": settings.username,
        "smtp_from_email": settings.from_email,
        "smtp_from_name": settings.from_name,
        "smtp_use_tls": str(settings.use_tls).lower(),
    }
    for key, value in mapping.items():
        await _set_setting(db, key, value, current_user.id)

    # Only update password if provided (not None)
    if settings.password is not None:
        await _set_setting(db, "smtp_password", settings.password, current_user.id)

    await db.commit()
    return await get_smtp_settings(db)


@router.post("/smtp/test", dependencies=[Depends(require_roles(WRITE_ADMIN_ROLES))])
async def test_smtp(
    req: SmtpTestRequest,
    db: AsyncSession = Depends(get_db),
):
    """Send a test email to verify SMTP configuration."""
    from utils.email_service import send_test_email
    try:
        result = await send_test_email(db, req.to_email)
        if result:
            return {"success": True, "message": f"Test email sent to {req.to_email}"}
        return {"success": False, "message": "SMTP is disabled or not configured"}
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to send test email: {str(e)}",
        )
