"""Pydantic schemas for LDAP and SAML SSO configuration."""
from pydantic import BaseModel, Field
from typing import Optional
from schemas._field_limits import (
    EMAIL,
    HOSTNAME,
    JSON_BLOB,
    NAME,
    SHORT_LABEL,
    TITLE,
    URL,
)


class LdapSettings(BaseModel):
    """LDAP configuration submitted by admin."""
    enabled: bool = False
    server_url: str = Field("", max_length=URL)
    bind_dn: str = Field("", max_length=TITLE)
    bind_password: Optional[str] = Field(None, max_length=NAME)  # None = keep existing
    search_base: str = Field("", max_length=TITLE)
    search_filter: str = Field("(uid={username})", max_length=TITLE)
    username_attribute: str = Field("uid", max_length=SHORT_LABEL)
    email_attribute: str = Field("mail", max_length=SHORT_LABEL)
    fullname_attribute: str = Field("cn", max_length=SHORT_LABEL)
    tls_enabled: bool = True
    tls_ca_cert: Optional[str] = Field(None, max_length=JSON_BLOB)  # PEM CA certificate, None = keep existing


class SamlSettings(BaseModel):
    """SAML 2.0 SSO configuration submitted by admin."""
    enabled: bool = False
    idp_entity_id: str = Field("", max_length=URL)
    idp_sso_url: str = Field("", max_length=URL)
    idp_slo_url: str = Field("", max_length=URL)
    idp_x509_cert: Optional[str] = Field(None, max_length=JSON_BLOB)  # None = keep existing
    sp_entity_id: str = Field("", max_length=URL)


class AuthSettingsResponse(BaseModel):
    """Combined auth settings returned to admin (passwords masked)."""
    ldap: LdapSettings
    saml: SamlSettings


class LdapTestRequest(BaseModel):
    """Test LDAP connection with a username/password."""
    username: str = Field(..., max_length=NAME)
    password: str = Field(..., max_length=NAME)


class AuthProvidersResponse(BaseModel):
    """Public endpoint response — which auth methods are available."""
    local: bool = True
    ldap: bool = False
    saml: bool = False
    saml_login_url: Optional[str] = None


class SmtpSettings(BaseModel):
    """SMTP / email configuration submitted by admin."""
    enabled: bool = False
    host: str = Field("", max_length=HOSTNAME)
    port: int = 587
    username: str = Field("", max_length=NAME)
    password: Optional[str] = Field(None, max_length=NAME)  # None = keep existing
    from_email: str = Field("", max_length=EMAIL)
    from_name: str = Field("RedWire", max_length=NAME)
    use_tls: bool = True


class SmtpTestRequest(BaseModel):
    """Send a test email."""
    # 254 is the RFC 5321 SMTP path limit. GHSA-8r3m-6x57-pg97 follow-up.
    to_email: str = Field(..., max_length=EMAIL)


class ForgotPasswordRequest(BaseModel):
    """Public forgot-password request."""
    # max_length caps unauth body allocation before the route runs
    # (GHSA-8r3m-6x57-pg97). 254 is the RFC 5321 limit.
    email: str = Field(..., max_length=254)


class ResetPasswordRequest(BaseModel):
    """Public reset-password request."""
    # token is a JWT (typically <1KB); 4096 is generous.
    # GHSA-8r3m-6x57-pg97.
    token: str = Field(..., max_length=4096)
    new_password: str = Field(..., max_length=256)

