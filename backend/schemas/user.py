from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime
from models.user import UserRole
from schemas.rbac import GroupResponse

class UserBase(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)
    email: EmailStr
    full_name: Optional[str] = None
    profile_photo: Optional[str] = None

class UserCreate(UserBase):
    password: str = Field(..., min_length=8)
    registration_code: Optional[str] = None

ALLOWED_THEMES = {"purple", "crimson", "blue", "emerald", "amber", "custom"}
ALLOWED_PALETTES = {"aurora", "operator", "half-dark", "light"}


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    profile_photo: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    group_ids: Optional[List[str]] = None
    theme_preference: Optional[str] = Field(None, max_length=32)
    theme_palette: Optional[str] = Field(None, max_length=32)
    theme_accent_custom: Optional[str] = Field(None, max_length=7)
    # Required when changing `email` on the self-update endpoint
    # (GHSA-hc9w-hggj-r52w): email is the password-reset identity,
    # so a credential-class proof-of-possession is required.
    current_password: Optional[str] = None
    totp_code: Optional[str] = Field(None, min_length=6, max_length=6)

class UserPasswordUpdate(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=8)
    totp_code: Optional[str] = Field(None, min_length=6, max_length=6)

class UserResponse(BaseModel):
    id: str
    username: str
    email: str  # plain str — external providers (LDAP/SAML) may use non-standard TLDs
    full_name: Optional[str] = None
    profile_photo: Optional[str] = None
    role: UserRole
    is_active: bool
    totp_enabled: bool = False
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

    username: str
    password: str
    totp_code: Optional[str] = None

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    requires_2fa: bool = False

class TokenRefresh(BaseModel):
    refresh_token: str

class TotpSetupResponse(BaseModel):
    secret: str
    qr_code: str
    otpauth_uri: str

class TotpVerifyRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6)

class TotpDisableRequest(BaseModel):
    password: str
    code: str = Field(..., min_length=6, max_length=6)
