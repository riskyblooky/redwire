"""Pydantic schemas for LDAP and SAML SSO configuration."""
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from schemas._field_limits import (
    EMAIL,
    HOSTNAME,
    JSON_BLOB,
    NAME,
    SHORT_LABEL,
    TITLE,
    URL,
)

# Explicit tri-state instead of the old `tls_enabled` bool. The bool was
# ambiguous: `true` + an ``ldap://`` URL used to *silently* leave the
# connection plaintext because the code set the TLS config on the Server
# object but never invoked StartTLS. Modes now map 1:1 to what actually
# happens on the wire:
#   * ``none``     — plain LDAP, no TLS at all
#   * ``ldaps``    — direct TLS from connect (URL should be ldaps://)
#   * ``starttls`` — plain LDAP connect, then Connection.start_tls() upgrade
TlsMode = Literal["none", "ldaps", "starttls"]


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
    tls_mode: TlsMode = "ldaps"
    # When false, the TLS handshake accepts any certificate (CERT_NONE).
    # For internal / self-signed servers where you can't ship a CA cert.
    # Logged loudly at auth time.
    tls_verify: bool = True
    tls_ca_cert: Optional[str] = Field(None, max_length=JSON_BLOB)  # PEM CA certificate, None = keep existing
    # When True, real logins log a per-step [LDAP DEBUG] trace to stdout
    # and the Test Connection endpoint returns the same trace inline. Off
    # by default; turn on temporarily while diagnosing a broken bind /
    # filter / TLS handshake.
    debug_enabled: bool = False

    @field_validator("tls_mode", mode="before")
    @classmethod
    def _coerce_tls_mode(cls, v):
        # Backward compat with older payloads that only had ``tls_enabled``:
        # a plain bool arrives here (True/False), so map it to the closest
        # equivalent mode. The router's read path also does this on GET.
        if isinstance(v, bool):
            return "ldaps" if v else "none"
        return v


class SamlSettings(BaseModel):
    """SAML 2.0 SSO configuration submitted by admin."""
    enabled: bool = False
    idp_entity_id: str = Field("", max_length=URL)
    idp_sso_url: str = Field("", max_length=URL)
    idp_slo_url: str = Field("", max_length=URL)
    idp_x509_cert: Optional[str] = Field(None, max_length=JSON_BLOB)  # None = keep existing
    sp_entity_id: str = Field("", max_length=URL)
    want_messages_signed: bool = False


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

