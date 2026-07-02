from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List
from datetime import datetime
import re
import unicodedata
from models.user import UserRole
from schemas.rbac import GroupResponse

# Username allowlist: 2-50 chars from [a-z0-9._-], must start AND end with
# an alphanumeric. Applied AFTER NFKC + casefold so fullwidth/Cyrillic/etc.
# collapse to their canonical form (or fail) before the regex runs.
# GHSA-2hrj-c2v3-8p2v.
_USERNAME_ALLOWED = re.compile(r"^[a-z0-9][a-z0-9._-]{0,48}[a-z0-9]$")


# GHSA-fp33-983q-99r9 #4 (CWE-1240): bcrypt truncates inputs at 72 bytes
# and silently ignores anything beyond that. A user setting a password
# longer than 72 bytes actually only had the first 72 bytes protecting
# their account — anyone typing a different string with the same first
# 72 bytes could log in. Cap at the source (schema layer) rather than
# rely on the caller to enforce.
#
# The cap is on the UTF-8-encoded byte length, not the character count,
# because bcrypt operates on bytes. A 60-character emoji password would
# be well over 72 bytes and get truncated even though its len() reads
# below the cap.
def _validate_password_bcrypt_safe(v: str) -> str:
    encoded_len = len(v.encode("utf-8"))
    if encoded_len > 72:
        raise ValueError(
            f"Password exceeds bcrypt's 72-byte limit ({encoded_len} bytes). "
            "Choose a shorter password or one with fewer multi-byte characters."
        )
    return v


def normalize_username(v: str) -> str:
    """NFKC-normalize + casefold + strict ASCII allowlist.

    Closes the Unicode homograph spoof on registration (GHSA-2hrj-c2v3-8p2v).
    Order matters: NFKC first collapses fullwidth / compatibility forms into
    their canonical letters (so 'ａｄｍｉｎ' becomes 'admin' and gets caught by
    case-fold dedup against an existing 'admin'); casefold then handles
    cases the .lower() method misses (eszett, etc.). Anything not in the
    ASCII allowlist after that — Cyrillic 'а' (U+0430), control chars,
    invisibles, etc. — falls out at the regex.
    """
    v = unicodedata.normalize("NFKC", v).casefold()
    if not _USERNAME_ALLOWED.fullmatch(v):
        raise ValueError(
            "Username must be 2-50 ASCII chars from [a-z0-9._-] and must "
            "start and end with an alphanumeric (case-insensitive)."
        )
    return v


class UserBase(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)
    email: EmailStr = Field(..., max_length=254)  # RFC 5321
    full_name: Optional[str] = Field(None, max_length=255)
    profile_photo: Optional[str] = Field(None, max_length=255)

    @field_validator("username")
    @classmethod
    def _validate_username(cls, v: str) -> str:
        return normalize_username(v)

class UserCreate(UserBase):
    # max_length caps unauth body allocation before the route runs (GHSA-8r3m-6x57-pg97).
    # bcrypt truncates at 72 bytes, but 256 leaves headroom for future hashes (argon2 etc.).
    # The _validate_password_bcrypt_safe validator enforces the ACTUAL bcrypt-safe
    # byte cap of 72 (GHSA-fp33-983q-99r9 #4) — max_length is the alloc guard only.
    password: str = Field(..., min_length=8, max_length=256)
    registration_code: Optional[str] = Field(default=None, max_length=64)

    _v_password_bcrypt = field_validator("password")(_validate_password_bcrypt_safe)

ALLOWED_THEMES = {"purple", "crimson", "blue", "emerald", "amber", "custom"}
ALLOWED_PALETTES = {"aurora", "operator", "half-dark", "light"}


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = Field(None, max_length=254)
    full_name: Optional[str] = Field(None, max_length=255)
    profile_photo: Optional[str] = Field(None, max_length=255)
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    group_ids: Optional[List[str]] = None
    theme_preference: Optional[str] = Field(None, max_length=32)
    theme_palette: Optional[str] = Field(None, max_length=32)
    theme_accent_custom: Optional[str] = Field(None, max_length=7)
    # Required when changing `email` on the self-update endpoint
    # (GHSA-hc9w-hggj-r52w): email is the password-reset identity,
    # so a credential-class proof-of-possession is required.
    current_password: Optional[str] = Field(None, max_length=256)
    totp_code: Optional[str] = Field(None, min_length=6, max_length=6)

class UserPasswordUpdate(BaseModel):
    # max_length caps the per-request allocation. GHSA-8r3m-6x57-pg97 follow-up.
    old_password: str = Field(..., max_length=256)
    new_password: str = Field(..., min_length=8, max_length=256)
    totp_code: Optional[str] = Field(None, min_length=6, max_length=6)

    # GHSA-fp33-983q-99r9 #4: new_password gets the bcrypt-safe byte-length
    # check. old_password intentionally does NOT — legacy passwords set
    # before this validator landed may exceed 72 bytes; rejecting them at
    # verify time would lock the operator out of the password-change flow.
    _v_new_password_bcrypt = field_validator("new_password")(_validate_password_bcrypt_safe)

class UserResponse(BaseModel):
    id: str
    username: str
    email: str  # plain str — external providers (LDAP/SAML) may use non-standard TLDs
    full_name: Optional[str] = None
    profile_photo: Optional[str] = None
    role: UserRole
    is_active: bool
    totp_enabled: bool = False
    # Number of 2FA recovery codes still available for self-service
    # account recovery. The settings UI surfaces this so the user
    # knows when to regenerate. GHSA-vm6w-9wm5-q367 follow-up.
    recovery_codes_remaining: int = 0
    auth_provider: str = "local"
    must_change_password: bool = False
    created_at: datetime
    last_login: Optional[datetime] = None
    last_active: Optional[datetime] = None
    groups: List[GroupResponse] = []
    theme_preference: str = "purple"
    theme_palette: str = "aurora"
    theme_accent_custom: Optional[str] = None

    class Config:
        from_attributes = True

class UserSummary(BaseModel):
    id: str
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    profile_photo: Optional[str] = None
    role: UserRole

    class Config:
        from_attributes = True

class UserLogin(BaseModel):
    # max_length caps unauth body allocation before the route runs (GHSA-8r3m-6x57-pg97).
    username: str = Field(..., max_length=50)
    password: str = Field(..., max_length=256)
    totp_code: Optional[str] = Field(default=None, min_length=6, max_length=6)

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    requires_2fa: bool = False

class TokenRefresh(BaseModel):
    # /auth/refresh has no @limiter decorator and the value is fed through
    # decode_token -> jwt.decode -- O(n) over attacker-controlled data.
    # max_length caps the per-request allocation. GHSA-8r3m-6x57-pg97.
    refresh_token: str = Field(..., max_length=4096)

class TotpSetupResponse(BaseModel):
    secret: str
    qr_code: str
    otpauth_uri: str

class TotpSetupRequest(BaseModel):
    # max_length caps body allocation before the route runs. GHSA-8r3m-6x57-pg97 follow-up.
    password: str = Field(..., max_length=256)

class TotpVerifyRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6)


class TwoFactorVerifyRequest(BaseModel):
    """Login-time 2FA submission. Accepts either a 6-digit TOTP code OR
    an 8-char alnum recovery code (``XXXX-XXXX``); dispatcher in the
    verify-2fa handler routes based on shape. GHSA-vm6w-9wm5-q367
    follow-up — replaces the digits-only ``TotpVerifyRequest`` at
    that endpoint.
    """
    # 6-char minimum covers TOTP; 24 is generous headroom for
    # whitespace/hyphens around an 8-char recovery code.
    code: str = Field(..., min_length=6, max_length=24)


class TotpVerifySetupResponse(BaseModel):
    """Response shape for ``POST /auth/totp/verify-setup``.

    ``recovery_codes`` is the *only* time the plaintext codes are sent.
    After this response, only bcrypt hashes are stored. GHSA-vm6w-9wm5-q367.
    """
    message: str
    recovery_codes: List[str] = []


class RecoveryCodesRegenerateRequest(BaseModel):
    """Body for ``POST /auth/totp/recovery-codes/regenerate``.
    Requires both the password and a valid TOTP code — re-issuing
    recovery codes is a credential-class event, same shape as
    ``/totp/disable``.
    """
    password: str = Field(..., max_length=256)
    code: str = Field(..., min_length=6, max_length=6)


class RecoveryCodesResponse(BaseModel):
    """Response shape for the regenerate endpoint. Same one-shot
    plaintext-then-hash discipline as the verify-setup response."""
    recovery_codes: List[str] = []


class TotpDisableRequest(BaseModel):
    # max_length caps body allocation before the route runs (GHSA-8r3m-6x57-pg97).
    password: str = Field(..., max_length=256)
    code: str = Field(..., min_length=6, max_length=6)
