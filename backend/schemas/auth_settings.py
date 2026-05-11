"""Pydantic schemas for LDAP and SAML SSO configuration."""
from pydantic import BaseModel
from typing import Optional


class LdapSettings(BaseModel):
    """LDAP configuration submitted by admin."""
    enabled: bool = False
    server_url: str = ""
    bind_dn: str = ""
    bind_password: Optional[str] = None  # None = keep existing
    search_base: str = ""
    search_filter: str = "(uid={username})"
    username_attribute: str = "uid"
    email_attribute: str = "mail"
    fullname_attribute: str = "cn"
    tls_enabled: bool = True
    tls_ca_cert: Optional[str] = None  # PEM CA certificate, None = keep existing


class SamlSettings(BaseModel):
    """SAML 2.0 SSO configuration submitted by admin."""
    enabled: bool = False
    idp_entity_id: str = ""
    idp_sso_url: str = ""
    idp_slo_url: str = ""
    idp_x509_cert: Optional[str] = None  # None = keep existing
    sp_entity_id: str = ""


class AuthSettingsResponse(BaseModel):
    """Combined auth settings returned to admin (passwords masked)."""
    ldap: LdapSettings
    saml: SamlSettings


class LdapTestRequest(BaseModel):
    """Test LDAP connection with a username/password."""
    username: str
    password: str


class AuthProvidersResponse(BaseModel):
    """Public endpoint response — which auth methods are available."""
    local: bool = True
    ldap: bool = False
    saml: bool = False
    saml_login_url: Optional[str] = None


class SmtpSettings(BaseModel):
    """SMTP / email configuration submitted by admin."""
    enabled: bool = False
    host: str = ""
    port: int = 587
    username: str = ""
    password: Optional[str] = None  # None = keep existing
    from_email: str = ""
    from_name: str = "RedWire"
    use_tls: bool = True


class SmtpTestRequest(BaseModel):
    """Send a test email."""
    to_email: str


class ForgotPasswordRequest(BaseModel):
    """Public forgot-password request."""
    email: str


class ResetPasswordRequest(BaseModel):
    """Public reset-password request."""
    token: str
    new_password: str

