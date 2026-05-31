from typing import Optional
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db
from models.user import User, UserRole
from models.auth_settings import AuthSetting
from schemas.user import (
    UserLogin, Token, UserCreate, UserResponse,
    TotpSetupResponse, TotpSetupRequest, TotpVerifyRequest, TotpDisableRequest,
)
from schemas.auth_settings import AuthProvidersResponse, ForgotPasswordRequest, ResetPasswordRequest
from auth import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    blacklist_token,
    is_token_blacklisted,
    generate_totp_secret,
    get_totp_uri,
    generate_qr_base64,
    verify_totp_code,
    authenticate_ldap,
    build_saml_request_url,
    process_saml_response,
    generate_sp_metadata,
)
from datetime import datetime, timedelta
import os
import uuid
import logging
from rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["authentication"])
security = HTTPBearer()

# Refresh token is set as an HttpOnly, SameSite=Strict cookie scoped to "/"
# (the browser-visible path; Nginx may rewrite /api/auth -> /auth on the way
# to the backend, so the cookie has to be set at the browser's path root).
# An empty string is still returned in the JSON body for response-model
# compatibility, but the only value a client can use is the cookie.
# GHSA-gv65-p25x-qrqj.
REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_MAX_AGE = 60 * 60 * 24  # 24h — matches create_refresh_token


def _set_refresh_cookie(response: Response, request: Request, refresh_token: str) -> None:
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        refresh_token,
        max_age=REFRESH_COOKIE_MAX_AGE,
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https",
        path="/",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE_NAME, path="/")

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Get current authenticated user information."""
    return current_user

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("3/minute")
async def register(request: Request, user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    """Register a new user."""
    # Check if username already exists
    result = await db.execute(select(User).where(User.username == user_data.username))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    
    # Check if email already exists
    result = await db.execute(select(User).where(User.email == user_data.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Validate registration code
    # We require a code unless strictly disabled (which we won't do for now)
    if not user_data.registration_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Registration code is required"
        )
    
    from models.registration_code import RegistrationCode
    
    # Check code validity
    reg_code = await db.execute(
        select(RegistrationCode).where(RegistrationCode.code == user_data.registration_code)
    )
    reg_code = reg_code.scalar_one_or_none()
    
    if not reg_code:
        raise HTTPException(status_code=400, detail="Invalid registration code")
        
    if not reg_code.is_active:
        raise HTTPException(status_code=400, detail="Registration code is inactive")
        
    if reg_code.expires_at and reg_code.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Registration code has expired")
        
    if reg_code.used_count >= reg_code.max_uses:
        raise HTTPException(status_code=400, detail="Registration code usage limit reached")
    
    # Create new user
    hashed_password = get_password_hash(user_data.password)
    new_user = User(
        username=user_data.username,
        email=user_data.email,
        full_name=user_data.full_name,
        hashed_password=hashed_password,
        role=UserRole.OPERATOR,
        registration_code_id=reg_code.id,
    )
    
    db.add(new_user)
    await db.flush()  # Materialize new_user.id before using it in user_groups
    
    # Increment used count
    reg_code.used_count += 1
    
    # Auto-assign to default group
    from models.group import Group, user_groups
    default_group_result = await db.execute(
        select(Group).where(Group.is_default == True)
    )
    default_group = default_group_result.scalar_one_or_none()
    if default_group:
        await db.execute(
            user_groups.insert().values(user_id=new_user.id, group_id=default_group.id)
        )
    
    await db.commit()
    
    # Re-fetch user with groups loaded to prevent MissingGreenlet error
    # triggered by Pydantic accessing lazy-loaded relationship
    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(User)
        .where(User.id == new_user.id)
        .options(selectinload(User.groups))
    )
    new_user = result.scalar_one()
    
    return new_user

@router.post("/login")
@limiter.limit("5/minute")
async def login(request: Request, credentials: UserLogin, response: Response, db: AsyncSession = Depends(get_db)):
    """Authenticate user and return JWT tokens. Supports local, LDAP, and 2FA."""
    # Load auth settings (gracefully handle missing table if migration not yet applied)
    try:
        settings_result = await db.execute(select(AuthSetting))
        auth_cfg = {s.key: s.value or "" for s in settings_result.scalars().all()}
    except Exception:
        await db.rollback()
        auth_cfg = {}
    ldap_enabled = auth_cfg.get("ldap_enabled", "false").lower() == "true"

    # Find user by username
    result = await db.execute(select(User).where(User.username == credentials.username))
    user = result.scalar_one_or_none()

    authenticated = False
    # Capture the row's auth_provider up-front. Treat NULL/empty as
    # "local" for back-compat with rows that pre-date the column.
    provider = (user.auth_provider or "local") if user else None

    # Local password is only valid for local-auth users. Without this
    # guard, an SSO/LDAP-bound user whose `hashed_password` still
    # exists (because they migrated from local, or an admin reset
    # their password) can bypass the IdP indefinitely
    # (GHSA-39x9-f79h-rh4r issue 1).
    if user and provider == "local" and verify_password(credentials.password, user.hashed_password):
        authenticated = True

    # Try LDAP if local failed and LDAP is enabled
    if not authenticated and ldap_enabled:
        ldap_settings = {
            "server_url": auth_cfg.get("ldap_server_url", ""),
            "bind_dn": auth_cfg.get("ldap_bind_dn", ""),
            "bind_password": auth_cfg.get("ldap_bind_password", ""),
            "search_base": auth_cfg.get("ldap_search_base", ""),
            "search_filter": auth_cfg.get("ldap_search_filter", "(uid={username})"),
            "username_attribute": auth_cfg.get("ldap_username_attribute", "uid"),
            "email_attribute": auth_cfg.get("ldap_email_attribute", "mail"),
            "fullname_attribute": auth_cfg.get("ldap_fullname_attribute", "cn"),
            "tls_enabled": auth_cfg.get("ldap_tls_enabled", "true"),
            "tls_ca_cert": auth_cfg.get("ldap_tls_ca_cert", ""),
        }
        ldap_info = authenticate_ldap(credentials.username, credentials.password, ldap_settings)
        if ldap_info:
            authenticated = True
            # JIT provision: create local user if they don't exist
            if not user:
                from models.group import Group, user_groups
                new_user = User(
                    id=str(uuid.uuid4()),
                    username=ldap_info.get("username", credentials.username),
                    email=ldap_info.get("email", f"{credentials.username}@ldap.local"),
                    hashed_password=get_password_hash(str(uuid.uuid4())),  # random, can't login locally
                    full_name=ldap_info.get("full_name", ""),
                    role=UserRole.OPERATOR,
                    auth_provider="ldap",
                    is_active=True,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
                db.add(new_user)
                await db.flush()

                # Auto-assign to default group
                default_group_result = await db.execute(
                    select(Group).where(Group.is_default == True)
                )
                default_group = default_group_result.scalar_one_or_none()
                if default_group:
                    await db.execute(
                        user_groups.insert().values(user_id=new_user.id, group_id=default_group.id)
                    )
                await db.commit()
                user = new_user
                logger.info(f"JIT provisioned LDAP user: {user.username}")
            elif provider != "ldap":
                # An existing local- or SAML-bound row with the same
                # username is a collision, not the same identity.
                # Adopting it would let an LDAP entry with
                # uid=<existing-local-admin> assume that account's
                # role, engagements, and API tokens
                # (GHSA-39x9-f79h-rh4r issue 2).
                logger.warning(
                    "LDAP login for %r refused: existing user is auth_provider=%r",
                    credentials.username, provider,
                )
                authenticated = False

    if not authenticated or not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user account"
        )
    
    # 2FA check
    if user.totp_enabled and user.totp_secret:
        if not credentials.totp_code:
            # Password OK, but 2FA required — return partial token
            partial_token = create_access_token(
                data={"sub": user.id, "role": user.role.value, "2fa_pending": True},
                expires_delta=timedelta(minutes=5),
            )
            return {
                "access_token": partial_token,
                "refresh_token": "",
                "token_type": "bearer",
                "requires_2fa": True,
            }
        
        # Decrypt and verify the TOTP code
        from auth.crypto import decrypt_totp_secret
        decrypted_secret = decrypt_totp_secret(user.totp_secret)
        if not verify_totp_code(decrypted_secret, credentials.totp_code):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid two-factor authentication code",
            )
    
    # Update last login
    user.last_login = datetime.utcnow()
    await db.commit()
    
    # Create tokens
    access_token = create_access_token(data={"sub": user.id, "role": user.role.value})
    refresh_token = create_refresh_token(data={"sub": user.id})

    _set_refresh_cookie(response, request, refresh_token)
    return {
        "access_token": access_token,
        "refresh_token": "",
        "token_type": "bearer",
        "requires_2fa": False,
        "must_change_password": user.must_change_password,
    }

# ─── 2FA Verification (second step of login) ────────────────────────────────

@router.post(
    "/verify-2fa",
    summary="Complete 2FA login",
    description="Accepts a 2FA-pending token (from /auth/login) and a TOTP code. "
                "Returns a full JWT pair on success.",
)
@limiter.limit("5/minute")
async def verify_2fa(
    request: Request,
    body: TotpVerifyRequest,
    response: Response,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
):
    """Verify TOTP code using a 2FA-pending token and issue full JWT tokens."""
    token = credentials.credentials

    # Decode the pending token manually (get_current_user blocks 2fa_pending)
    payload = decode_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    if not payload.get("2fa_pending"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token is not a 2FA-pending token",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    if not user.totp_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA is not configured for this user",
        )

    # Decrypt and verify the TOTP code
    from auth.crypto import decrypt_totp_secret
    decrypted_secret = decrypt_totp_secret(user.totp_secret)
    if not verify_totp_code(decrypted_secret, body.code):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid two-factor authentication code",
        )

    # Blacklist the pending token so it can't be reused
    blacklist_token(token)

    # Update last login
    user.last_login = datetime.utcnow()
    await db.commit()

    # Issue full tokens
    access_token = create_access_token(data={"sub": user.id, "role": user.role.value})
    refresh_token = create_refresh_token(data={"sub": user.id})

    _set_refresh_cookie(response, request, refresh_token)
    return {
        "access_token": access_token,
        "refresh_token": "",
        "token_type": "bearer",
        "requires_2fa": False,
        "must_change_password": user.must_change_password,
    }

@router.post("/refresh", response_model=Token)
async def refresh_token_endpoint(
    refresh_token: Optional[str] = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Refresh access token using the refresh-token cookie.

    Only issues a new access token. The refresh-token cookie is reused
    (not rotated) so the session expires when its original expiry is
    reached (default 24h from login).

    The refresh token is read from an HttpOnly+SameSite=Strict cookie
    set by /auth/login (and friends); accepting it from the request body
    would defeat the cookie's XSS protection. GHSA-gv65-p25x-qrqj.
    """
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing refresh-token cookie"
        )
    if is_token_blacklisted(refresh_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has been revoked"
        )

    payload = decode_token(refresh_token)

    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )
    
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload"
        )
    
    # Get user
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )
    
    # Create new access token only — do NOT rotate the refresh token
    # so the session naturally expires when the refresh token does.
    # The refresh cookie is left in place untouched.
    access_token = create_access_token(data={"sub": user.id, "role": user.role.value})

    return {
        "access_token": access_token,
        "refresh_token": "",
        "token_type": "bearer"
    }

@router.post("/logout")
async def logout(
    response: Response,
    refresh_token: Optional[str] = Cookie(default=None),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
):
    """Logout user by blacklisting their current access token and refresh
    cookie, and clearing the refresh cookie from the browser.

    Client must discard the access token after this call.
    """
    access_token = credentials.credentials

    # Clear last_active so user shows as offline immediately
    try:
        payload = decode_token(access_token)
        if payload and "sub" in payload:
            user_id = payload["sub"]
            result = await db.execute(
                select(User).where(User.id == user_id)
            )
            user = result.scalar_one_or_none()
            if user:
                user.last_active = None
                await db.commit()
    except Exception:
        pass  # Don't fail logout if this errors

    # Blacklist the access token
    blacklist_token(access_token)
    # Blacklist the paired refresh token so /auth/refresh cannot
    # mint a new session after logout (GHSA-p97c-94pr-2m32 fix; the
    # token is now read from the HttpOnly cookie per GHSA-gv65-p25x-qrqj).
    if refresh_token:
        blacklist_token(refresh_token)
    _clear_refresh_cookie(response)

    return {"message": "Successfully logged out"}


# ─── Force Password Change ────────────────────────────────────────────────────

from pydantic import BaseModel, Field

class ForceChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)

@router.post(
    "/force-change-password",
    summary="Force change password",
    description="Allows a user whose must_change_password flag is set to change their password. "
                "Validates the current password, sets the new one, clears the flag, and returns fresh tokens.",
)
@limiter.limit("5/minute")
async def force_change_password(
    request: Request,
    body: ForceChangePasswordRequest,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change password for users flagged with must_change_password."""
    if not current_user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password change is not required",
        )

    # Verify current password
    if not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect current password",
        )

    # Prevent reusing the same password
    if verify_password(body.new_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different from current password",
        )

    # Update password and clear the flag
    current_user.hashed_password = get_password_hash(body.new_password)
    current_user.must_change_password = False
    current_user.updated_at = datetime.utcnow()
    await db.commit()
    
    # Revoke all existing sessions so old tokens become invalid
    from auth.jwt import revoke_all_user_tokens
    revoke_all_user_tokens(current_user.id)

    # Issue fresh tokens
    access_token = create_access_token(data={"sub": current_user.id, "role": current_user.role.value})
    refresh_token = create_refresh_token(data={"sub": current_user.id})

    _set_refresh_cookie(response, request, refresh_token)
    return {
        "access_token": access_token,
        "refresh_token": "",
        "token_type": "bearer",
        "message": "Password changed successfully",
    }


# ─── TOTP Two-Factor Authentication ──────────────────────────────────────────

@router.post(
    "/totp/setup",
    response_model=TotpSetupResponse,
    summary="Begin 2FA setup",
    description="Generates a TOTP secret and returns a QR code for authenticator app enrollment. "
                "2FA is not enabled until the code is verified via /auth/totp/verify-setup.",
)
@limiter.limit("5/minute")
async def totp_setup(
    request: Request,
    body: TotpSetupRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate TOTP secret and QR code for 2FA setup."""
    if current_user.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Two-factor authentication is already enabled",
        )

    # SSO/LDAP users authenticate via their identity provider; there's no
    # local hashed_password to verify against, and the IdP is the right
    # place to manage MFA for them. Refuse setup here rather than fall
    # through to verify_password() (which would fail for any input).
    if current_user.auth_provider != "local":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Two-factor authentication is managed by your identity provider.",
        )

    # Require the current password before binding a new second factor —
    # mirrors /totp/disable, which already enforces this. Without this
    # check, a stolen session token alone is enough to enroll the
    # account into an attacker-controlled authenticator and permanently
    # lock the legitimate owner out.
    if not verify_password(body.password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password",
        )

    secret = generate_totp_secret()
    uri = get_totp_uri(secret, current_user.username)
    qr_code = generate_qr_base64(uri)
    
    # Encrypt and store secret (not yet enabled until verified)
    from auth.crypto import encrypt_totp_secret
    current_user.totp_secret = encrypt_totp_secret(secret)
    await db.commit()
    
    return TotpSetupResponse(secret=secret, qr_code=qr_code, otpauth_uri=uri)


@router.post(
    "/totp/verify-setup",
    summary="Complete 2FA setup",
    description="Verifies a 6-digit TOTP code against the stored secret to finish enrollment. "
                "On success, 2FA is permanently enabled for the user.",
)
@limiter.limit("5/minute")
async def totp_verify_setup(
    request: Request,
    body: TotpVerifyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Verify TOTP code to complete 2FA setup and enable it."""
    if not current_user.totp_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="TOTP setup has not been initiated. Call /auth/totp/setup first.",
        )
    
    if current_user.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Two-factor authentication is already enabled",
        )
    
    from auth.crypto import decrypt_totp_secret
    decrypted_secret = decrypt_totp_secret(current_user.totp_secret)
    if not verify_totp_code(decrypted_secret, body.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid TOTP code. Please try again.",
        )
    
    current_user.totp_enabled = True
    current_user.totp_verified_at = datetime.utcnow()
    await db.commit()

    # MFA boundary changed: invalidate every existing session and
    # long-lived API token so a stolen pre-2FA bearer cannot survive
    # the user enabling 2FA (mirrors the password-change path).
    from auth.jwt import revoke_all_user_tokens
    from sqlalchemy import update as _sa_update
    from models.api_token import ApiToken
    revoke_all_user_tokens(current_user.id)
    await db.execute(
        _sa_update(ApiToken)
        .where(ApiToken.user_id == current_user.id)
        .values(is_active=False)
    )
    await db.commit()

    return {"message": "Two-factor authentication enabled successfully"}


@router.post(
    "/totp/disable",
    summary="Disable 2FA",
    description="Turns off two-factor authentication. Requires the user's current password "
                "and a valid TOTP code as confirmation.",
)
@limiter.limit("5/minute")
async def totp_disable(
    request: Request,
    body: TotpDisableRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Disable 2FA. Requires current password and a valid TOTP code."""
    if not current_user.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Two-factor authentication is not enabled",
        )
    
    # Verify password
    if not verify_password(body.password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password",
        )
    
    # Decrypt and verify TOTP code
    from auth.crypto import decrypt_totp_secret
    decrypted_secret = decrypt_totp_secret(current_user.totp_secret)
    if not verify_totp_code(decrypted_secret, body.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid TOTP code",
        )
    
    current_user.totp_secret = None
    current_user.totp_enabled = False
    current_user.totp_verified_at = None
    await db.commit()

    # MFA boundary changed: invalidate every existing session and
    # long-lived API token so a stolen post-2FA bearer cannot survive
    # the user disabling 2FA (mirrors the password-change path).
    from auth.jwt import revoke_all_user_tokens
    from sqlalchemy import update as _sa_update
    from models.api_token import ApiToken
    revoke_all_user_tokens(current_user.id)
    await db.execute(
        _sa_update(ApiToken)
        .where(ApiToken.user_id == current_user.id)
        .values(is_active=False)
    )
    await db.commit()

    return {"message": "Two-factor authentication disabled successfully"}


# ─── SAML SSO Endpoints ──────────────────────────────────────────────────────

@router.get(
    "/providers",
    response_model=AuthProvidersResponse,
    summary="List auth providers",
    description="Public endpoint reporting which authentication methods (local, LDAP, SAML SSO) are enabled.",
)
async def get_auth_providers(db: AsyncSession = Depends(get_db)):
    """Public endpoint: which authentication methods are available."""
    try:
        settings_result = await db.execute(select(AuthSetting))
        cfg = {s.key: s.value or "" for s in settings_result.scalars().all()}
    except Exception:
        await db.rollback()
        cfg = {}

    ldap_on = cfg.get("ldap_enabled", "false").lower() == "true"
    saml_on = cfg.get("saml_enabled", "false").lower() == "true"

    backend_url = os.getenv("BACKEND_URL", "http://localhost:8000")
    saml_login = f"{backend_url}/auth/saml/login" if saml_on else None

    return AuthProvidersResponse(
        local=True,
        ldap=ldap_on,
        saml=saml_on,
        saml_login_url=saml_login,
    )


@router.get(
    "/saml/login",
    summary="SAML SSO login redirect",
    description="Builds a SAML AuthnRequest and redirects (302) to the IdP SSO URL.",
)
async def saml_login(request: Request, db: AsyncSession = Depends(get_db)):
    """Redirect user to IdP for SAML SSO login."""
    settings_result = await db.execute(select(AuthSetting))
    cfg = {s.key: s.value or "" for s in settings_result.scalars().all()}

    if cfg.get("saml_enabled", "false").lower() != "true":
        raise HTTPException(status_code=400, detail="SAML SSO is not enabled")

    # Build settings dict without ldap_ prefix
    saml_cfg = {
        "idp_entity_id": cfg.get("saml_idp_entity_id", ""),
        "idp_sso_url": cfg.get("saml_idp_sso_url", ""),
        "idp_slo_url": cfg.get("saml_idp_slo_url", ""),
        "idp_x509_cert": cfg.get("saml_idp_x509_cert", ""),
        "sp_entity_id": cfg.get("saml_sp_entity_id", ""),
    }

    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    redirect_url, request_id = build_saml_request_url(
        saml_cfg, return_to=frontend_url + "/dashboard"
    )

    if not redirect_url:
        raise HTTPException(status_code=500, detail="Failed to generate SAML login request")

    response = RedirectResponse(url=redirect_url)
    # Bind the upcoming ACS callback to *this* AuthnRequest. The cookie is a
    # short-lived signed JWT so the request_id can't be forged or fixed by an
    # attacker. ACS rejects any Response that doesn't carry it.
    response.set_cookie(
        "saml_request_id",
        create_access_token(
            data={"sub": "saml_request", "type": "saml_request",
                  "saml_req": request_id},
            expires_delta=timedelta(minutes=10),
        ),
        max_age=600,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
    )
    return response


@router.post(
    "/saml/acs",
    summary="SAML ACS callback",
    description="Assertion Consumer Service — processes the IdP SAML response, "
                "JIT-provisions the user if new, and redirects to the frontend with JWT tokens.",
)
async def saml_acs(request: Request, db: AsyncSession = Depends(get_db)):
    """SAML Assertion Consumer Service — processes IdP response, JIT provisions user."""
    form_data = await request.form()
    post_data = {k: v for k, v in form_data.items()}

    logger.info(f"SAML ACS: received POST with keys: {list(post_data.keys())}")
    logger.info(f"SAML ACS: request.url = {request.url}")

    settings_result = await db.execute(select(AuthSetting))
    cfg = {s.key: s.value or "" for s in settings_result.scalars().all()}

    if cfg.get("saml_enabled", "false").lower() != "true":
        # Same gate as /saml/login. Without it the ACS will try to validate
        # a Response against an empty IdP cert.
        raise HTTPException(status_code=400, detail="SAML SSO is not enabled")

    # The Response must answer an AuthnRequest *we* issued. /saml/login set
    # a signed cookie carrying that request's ID; without it the Response is
    # unsolicited (IdP-initiated, replayed, or CSRF-driven) and is refused.
    request_id = None
    cookie = request.cookies.get("saml_request_id")
    if cookie:
        payload = decode_token(cookie) or {}
        if payload.get("type") == "saml_request":
            request_id = payload.get("saml_req")
    if not request_id:
        logger.warning("SAML ACS: no/invalid saml_request_id cookie — "
                       "unsolicited Response refused")
        raise HTTPException(
            status_code=400,
            detail="SAML response is unsolicited or the login request has "
                   "expired; start again at /auth/saml/login",
        )

    saml_cfg = {
        "idp_entity_id": cfg.get("saml_idp_entity_id", ""),
        "idp_sso_url": cfg.get("saml_idp_sso_url", ""),
        "idp_slo_url": cfg.get("saml_idp_slo_url", ""),
        "idp_x509_cert": cfg.get("saml_idp_x509_cert", ""),
        "sp_entity_id": cfg.get("saml_sp_entity_id", ""),
    }
    logger.info(f"SAML ACS: sp_entity_id = {saml_cfg['sp_entity_id']}")
    logger.info(f"SAML ACS: idp_entity_id = {saml_cfg['idp_entity_id']}")

    # Use the external URL (BACKEND_URL) for SAML response validation,
    # not request.url which reflects the internal proxy URL
    backend_url = os.getenv("BACKEND_URL", "http://localhost:8000")
    request_url = f"{backend_url}/auth/saml/acs"
    logger.info(f"SAML ACS: using request_url = {request_url}")
    user_info = process_saml_response(post_data, saml_cfg, request_url,
                                       request_id=request_id)

    if not user_info:
        logger.error("SAML ACS: process_saml_response returned None — auth failed")
        raise HTTPException(status_code=401, detail="SAML authentication failed")

    email = user_info.get("email", "")
    username = user_info.get("username", "")

    if not email:
        raise HTTPException(status_code=400, detail="No email in SAML assertion")

    # Find or create user. Match on email only — including username here
    # lets an assertion with username="admin" adopt an unrelated local row.
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user and (user.auth_provider or "local") != "saml":
        # An existing local/LDAP user with the same email is a collision,
        # not the same identity. Adopting the row would hand the assertion
        # holder that user's role and silently flip their auth_provider.
        logger.warning(
            "SAML ACS: assertion email %r collides with existing "
            "auth_provider=%r user — refusing",
            email, user.auth_provider,
        )
        raise HTTPException(
            status_code=403,
            detail="A non-SAML account already exists for this email",
        )

    if not user:
        # JIT provision
        from models.group import Group, user_groups
        user = User(
            id=str(uuid.uuid4()),
            username=username or email.split("@")[0],
            email=email,
            hashed_password=get_password_hash(str(uuid.uuid4())),
            full_name=user_info.get("full_name", ""),
            role=UserRole.OPERATOR,
            auth_provider="saml",
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(user)
        await db.flush()

        default_group_result = await db.execute(
            select(Group).where(Group.is_default == True)
        )
        default_group = default_group_result.scalar_one_or_none()
        if default_group:
            await db.execute(
                user_groups.insert().values(user_id=user.id, group_id=default_group.id)
            )
        logger.info(f"JIT provisioned SAML user: {user.username}")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="User account is disabled")

    user.last_login = datetime.utcnow()
    await db.commit()

    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")

    # If user has 2FA enabled, issue a partial token and redirect to 2FA challenge
    if user.totp_enabled and user.totp_secret:
        partial_token = create_access_token(
            data={"sub": user.id, "role": user.role.value, "2fa_pending": True},
            expires_delta=timedelta(minutes=5),
        )
        redirect_url = f"{frontend_url}/sso/callback#requires_2fa=true&access_token={partial_token}"
        response = RedirectResponse(url=redirect_url, status_code=302)
        response.delete_cookie("saml_request_id")
        return response

    # No 2FA — issue full tokens
    access_token = create_access_token(data={"sub": user.id, "role": user.role.value})
    refresh_token = create_refresh_token(data={"sub": user.id})

    # The access token still rides the URL fragment so the SPA can pick it up
    # from window.location.hash; the refresh token is set as an HttpOnly
    # cookie instead of being echoed into the URL, so it never reaches
    # localStorage. GHSA-gv65-p25x-qrqj.
    redirect_url = f"{frontend_url}/sso/callback#access_token={access_token}"
    response = RedirectResponse(url=redirect_url, status_code=302)
    response.delete_cookie("saml_request_id")
    _set_refresh_cookie(response, request, refresh_token)
    return response


@router.get(
    "/saml/metadata",
    summary="SP metadata XML",
    description="Returns SAML Service Provider metadata XML for configuring the Identity Provider.",
)
async def saml_metadata(db: AsyncSession = Depends(get_db)):
    """Serve SP metadata XML for IdP configuration."""
    settings_result = await db.execute(select(AuthSetting))
    cfg = {s.key: s.value or "" for s in settings_result.scalars().all()}

    saml_cfg = {
        "idp_entity_id": cfg.get("saml_idp_entity_id", ""),
        "idp_sso_url": cfg.get("saml_idp_sso_url", ""),
        "idp_slo_url": cfg.get("saml_idp_slo_url", ""),
        "idp_x509_cert": cfg.get("saml_idp_x509_cert", ""),
        "sp_entity_id": cfg.get("saml_sp_entity_id", ""),
    }

    metadata = generate_sp_metadata(saml_cfg)
    if not metadata:
        raise HTTPException(status_code=500, detail="Failed to generate SP metadata")

    return Response(content=metadata, media_type="application/xml")


# ─── Login Splash / Banner ────────────────────────────────────────────────────

@router.get(
    "/splash",
    summary="Get login splash screen config",
    description="Public endpoint — returns the splash screen / DoD banner config for the login page.",
)
async def get_splash_config(db: AsyncSession = Depends(get_db)):
    """Return splash screen config (public, no auth required)."""
    result = await db.execute(
        select(AuthSetting).where(AuthSetting.key.in_([
            "splash_enabled", "splash_title", "splash_message"
        ]))
    )
    settings = {s.key: s.value or "" for s in result.scalars().all()}

    return {
        "enabled": settings.get("splash_enabled", "false").lower() == "true",
        "title": settings.get("splash_title", ""),
        "message": settings.get("splash_message", ""),
    }


# ── Password Reset (Public) ────────────────────────────────────────────────────

@router.post(
    "/forgot-password",
    summary="Request password reset email",
    description="Public endpoint — sends a password reset email if the email exists. "
                "Always returns 200 to prevent user enumeration.",
)
async def forgot_password(
    req: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """Generate a reset token and send a password reset email."""
    from utils.email_service import send_password_reset_email

    # Always return success to prevent user enumeration
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()

    if user and user.auth_provider == "local":
        # Generate a short-lived reset token (30 minutes)
        reset_token = create_access_token(
            data={"sub": user.id, "type": "password_reset"},
            expires_delta=timedelta(minutes=30),
        )

        frontend_url = os.getenv("FRONTEND_URL", "https://localhost:8443")
        reset_url = f"{frontend_url}/reset-password?token={reset_token}"

        try:
            await send_password_reset_email(db, user.email, reset_url, user.username)
        except Exception as e:
            logger.error(f"Failed to send reset email to {user.email}: {e}")

    return {"message": "If an account with that email exists, a password reset link has been sent."}


@router.post(
    "/reset-password",
    summary="Reset password with token",
    description="Public endpoint — resets the user's password using a valid reset token.",
)
async def reset_password(
    req: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """Validate reset token and update the user's password."""

    # Decode and validate the reset token
    payload = decode_token(req.token)
    if not payload:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    # Must be a password_reset token (not an access/refresh token)
    if payload.get("type") != "password_reset":
        raise HTTPException(status_code=400, detail="Invalid token type")

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=400, detail="Invalid reset token")

    if user.auth_provider != "local":
        raise HTTPException(
            status_code=400,
            detail="Password reset is only available for local accounts. "
                   "Please use your SSO/LDAP provider to reset your password.",
        )

    # Validate password length
    if len(req.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    # Update password. Also clear TOTP — the email-reset flow is the
    # last-resort recovery path, and if 2FA was bound to an attacker
    # (e.g. via a stolen session before GHSA-vm6w-9wm5-q367 shipped),
    # the legitimate owner needs to be able to recover via email
    # without being blocked at the TOTP prompt forever.
    user.hashed_password = get_password_hash(req.new_password)
    user.must_change_password = False
    user.totp_enabled = False
    user.totp_secret = None
    user.totp_verified_at = None
    await db.commit()
    
    # Blacklist the reset token so it cannot be replayed
    from auth.jwt import blacklist_token
    blacklist_token(req.token)
    
    # Revoke all existing sessions
    from auth.jwt import revoke_all_user_tokens
    revoke_all_user_tokens(user.id)

    logger.info(f"Password reset completed for user {user.username}")
    return {"message": "Password has been reset successfully. You can now log in with your new password."}
