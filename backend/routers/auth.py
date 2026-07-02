from typing import Optional
from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, HTTPException, Response, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import AsyncSessionLocal, get_db
from models.user import User, UserRole
from models.auth_settings import AuthSetting
from schemas.user import (
    UserLogin, Token, UserCreate, UserResponse,
    TotpSetupResponse, TotpSetupRequest, TotpVerifyRequest,
    TotpVerifySetupResponse, TotpDisableRequest,
    TwoFactorVerifyRequest, RecoveryCodesRegenerateRequest, RecoveryCodesResponse,
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


# Reserved usernames refused at the registration boundary. Belt-and-
# suspenders defense alongside the GHSA-28f5-4wcg-9pwv "any admin exists?"
# seeder gate: even if that gate fails open (regression, future refactor,
# bug), an attacker can no longer squat on the configured ADMIN_USERNAME
# during the brief window before first boot finishes seeding. The set is
# rebuilt per-request rather than cached at import time so a deployment
# that rotates ADMIN_USERNAME via env var picks up the new value on the
# next register call.
_BASE_RESERVED_USERNAMES = frozenset({
    "admin", "administrator", "root", "system", "redwire",
})


def _reserved_usernames() -> frozenset[str]:
    extra: set[str] = set()
    configured = (os.environ.get("ADMIN_USERNAME") or "").strip().casefold()
    if configured:
        extra.add(configured)
    return _BASE_RESERVED_USERNAMES | extra
import logging
from rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["authentication"])
security = HTTPBearer()

# GHSA-fp33-983q-99r9 #1 (CWE-208): the login handler used to short-circuit
# on `if user and verify_password(...)`. When the username didn't exist the
# bcrypt cost was skipped entirely, so the response time revealed whether an
# account existed — a username-enumeration oracle for the unauth login
# surface. Precompute a valid Fernet-safe bcrypt hash at module import so
# the "no such user" branch can burn the same round of bcrypt work,
# producing a constant-time login response regardless of whether the
# username exists. The plaintext behind it is UUID4 random and never
# stored anywhere; only its hash is used.
_DUMMY_PASSWORD_HASH = get_password_hash(uuid.uuid4().hex)

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
    # GHSA-fp33-983q-99r9 #2 (CWE-204): validate the registration code
    # BEFORE any per-user existence check, and use a single generic
    # error for every pre-create failure. Prior order revealed:
    #   1. distinct 400s for "username taken" vs "email taken" — email
    #      enumeration vector for the unauth registration surface;
    #   2. registration-code validity was checked LAST, so an attacker
    #      without a code could still probe username/email existence.
    # Restructured: no-code / bad-code / stale-code / expired-code all
    # fail with "Registration failed" before we touch the users table.
    # The reserved-username check runs first so a well-known false
    # positive on the internal ADMIN name doesn't leak either.
    _GENERIC_REGISTER_ERROR = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Registration failed",
    )

    # GHSA-28f5-4wcg-9pwv follow-up: refuse the bootstrap admin username
    # (and well-known aliases) at the registration boundary so the seeder
    # gate isn't load-bearing on its own. UserCreate already runs the
    # NFKC-normalize + casefold via the username validator, so the value
    # we compare against the reserved set is in the same canonical form.
    # Keep the specific "That username is reserved" message — the
    # reserved set is publicly documented and the value doesn't leak
    # anything an attacker couldn't already guess.
    if user_data.username in _reserved_usernames():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="That username is reserved.",
        )

    # Validate registration code FIRST.
    if not user_data.registration_code:
        raise _GENERIC_REGISTER_ERROR

    from models.registration_code import RegistrationCode

    # Check code validity. .with_for_update() takes an exclusive PostgreSQL
    # row lock so concurrent registrations for the same code serialize at
    # the SELECT instead of all reading the same pre-increment used_count
    # under their own MVCC snapshot — the TOCTOU at the heart of
    # GHSA-552x-cmhc-wfg9. The lock is held until db.commit() below.
    reg_code = await db.execute(
        select(RegistrationCode)
        .where(RegistrationCode.code == user_data.registration_code)
        .with_for_update()
    )
    reg_code = reg_code.scalar_one_or_none()

    if (
        not reg_code
        or not reg_code.is_active
        or (reg_code.expires_at and reg_code.expires_at < datetime.utcnow())
        or reg_code.used_count >= reg_code.max_uses
    ):
        raise _GENERIC_REGISTER_ERROR

    # Now the code is known-good; check user uniqueness with a unified
    # error so username / email cases are indistinguishable to the
    # caller. An attacker with a valid registration code IS a
    # semi-trusted user (they were given the code by an admin) but the
    # enumeration risk still exists at the registration surface, so
    # keep the response uniform.
    result = await db.execute(select(User).where(User.username == user_data.username))
    if result.scalar_one_or_none():
        raise _GENERIC_REGISTER_ERROR
    result = await db.execute(select(User).where(User.email == user_data.email))
    if result.scalar_one_or_none():
        raise _GENERIC_REGISTER_ERROR
    
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
    #
    # GHSA-fp33-983q-99r9 #1: run bcrypt EXACTLY ONCE per request so
    # response time doesn't reveal user existence. Structure: pick the
    # hash to check against BEFORE running bcrypt (real hash when the
    # user is local, dummy otherwise), then gate the authenticated
    # flag on both the verify result AND the user-exists-and-is-local
    # conditions. The naive "if user and verify" short-circuits when
    # user is None, and adding "else: verify(dummy)" would pay TWO
    # bcrypt rounds on the wrong-password case (real hash + dummy)
    # which still leaks — hence this single-call shape.
    hash_to_check = (
        user.hashed_password if (user and provider == "local") else _DUMMY_PASSWORD_HASH
    )
    verify_ok = verify_password(credentials.password, hash_to_check)
    if user and provider == "local" and verify_ok:
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
            # New TLS controls — _resolve_tls_mode falls back to
            # ``tls_enabled`` when ``tls_mode`` is absent, so older installs
            # still authenticate as they did before.
            "tls_mode": auth_cfg.get("ldap_tls_mode", ""),
            "tls_verify": auth_cfg.get("ldap_tls_verify", "true"),
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
        matched_step = verify_totp_code(
            decrypted_secret, credentials.totp_code, user.totp_last_timestep
        )
        if matched_step is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or already-used two-factor authentication code",
            )
        user.totp_last_timestep = matched_step

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
    description="Accepts a 2FA-pending token (from /auth/login) and either a "
                "6-digit TOTP code OR an 8-char alnum recovery code "
                "(XXXX-XXXX). Returns a full JWT pair on success.",
)
@limiter.limit("5/minute")
async def verify_2fa(
    request: Request,
    body: TwoFactorVerifyRequest,
    response: Response,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
):
    """Verify TOTP code OR recovery code using a 2FA-pending token and
    issue full JWT tokens. GHSA-vm6w-9wm5-q367 follow-up: recovery
    codes are the self-service recovery path for a user who has lost
    their TOTP device but still remembers their password."""
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

    # Dispatch by shape: alphanumeric → recovery code, digits-only →
    # TOTP. The two are disjoint (TOTP is RFC 6238 digits-only; recovery
    # codes always contain at least one letter from the displayed
    # alphabet) so a single endpoint can route without ambiguity.
    from auth.recovery_codes import looks_like_recovery_code, verify_code as verify_recovery_code, normalise as normalise_recovery_code
    from models.recovery_code import RecoveryCode

    if looks_like_recovery_code(body.code):
        # ── Recovery-code path ─────────────────────────────────────
        # Walk unused rows for this user (bcrypt is constant-time per
        # row; iterating up to 10 hashes is ~1s worst-case miss).
        unused = await db.execute(
            select(RecoveryCode)
            .where(RecoveryCode.user_id == user.id)
            .where(RecoveryCode.used_at.is_(None))
        )
        rows = unused.scalars().all()

        matched: Optional[RecoveryCode] = None
        for rc in rows:
            if verify_recovery_code(body.code, rc.code_hash):
                matched = rc
                break

        if matched is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or already-used two-factor authentication code",
            )

        matched.used_at = datetime.utcnow()
        await db.commit()

        try:
            from utils.collaboration import create_activity_log
            await create_activity_log(
                db,
                engagement_id=None,
                user_id=user.id,
                action="consumed_recovery_code",
                resource_type="user",
                resource_id=user.id,
                resource_name=user.username,
                details="Consumed a 2FA recovery code at login",
            )
        except Exception:
            pass  # audit best-effort; don't block login
    else:
        # ── TOTP path (unchanged) ─────────────────────────────────
        from auth.crypto import decrypt_totp_secret
        decrypted_secret = decrypt_totp_secret(user.totp_secret)
        matched_step = verify_totp_code(
            decrypted_secret, body.code, user.totp_last_timestep
        )
        if matched_step is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or already-used two-factor authentication code",
            )
        user.totp_last_timestep = matched_step

    # Blacklist the pending token so it can't be reused. A silent failure
    # here would leave the 5-minute pending token live for replay; surface
    # it. GHSA-832g-v288-v593.
    if not blacklist_token(token):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Session revocation failed. Please retry.",
        )

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
    
    # Re-check the blacklist immediately before minting. The first check at
    # the top of the handler ran before the await above, so a
    # revoke_all_user_tokens that landed during the DB read would otherwise
    # be missed and the new access token would carry an iat > revocation_ts.
    # GHSA-832g-v288-v593 issue 3.
    if is_token_blacklisted(refresh_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has been revoked"
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

    # Blacklist the access token and the paired refresh token (read from
    # the HttpOnly cookie per GHSA-gv65-p25x-qrqj). A silent failure here
    # leaves the tokens live after a "successful" logout — surface the
    # failure instead. GHSA-832g-v288-v593.
    if not blacklist_token(access_token):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Session revocation failed. Please retry.",
        )
    if refresh_token:
        if not blacklist_token(refresh_token):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Session revocation failed. Please retry.",
            )
    _clear_refresh_cookie(response)

    return {"message": "Successfully logged out"}


# ─── Force Password Change ────────────────────────────────────────────────────

from pydantic import BaseModel, Field

class ForceChangePasswordRequest(BaseModel):
    # max_length caps body allocation before the route runs. GHSA-8r3m-6x57-pg97 follow-up.
    current_password: str = Field(..., max_length=256)
    new_password: str = Field(..., min_length=8, max_length=256)

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
    
    # Revoke all existing sessions so old tokens become invalid. The
    # password has already been committed; if the revoke fails the change
    # is in place but old sessions live, which we must surface rather than
    # silently no-op. GHSA-832g-v288-v593.
    from auth.jwt import revoke_all_user_tokens
    if not revoke_all_user_tokens(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Session revocation failed. Please retry.",
        )

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
    response_model=TotpVerifySetupResponse,
    summary="Complete 2FA setup",
    description="Verifies a 6-digit TOTP code against the stored secret to finish enrollment. "
                "On success, 2FA is permanently enabled and 10 single-use "
                "recovery codes are issued — shown ONCE in this response, "
                "never recoverable afterwards.",
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
    matched_step = verify_totp_code(
        decrypted_secret, body.code, current_user.totp_last_timestep
    )
    if matched_step is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or already-used TOTP code. Please try again.",
        )
    current_user.totp_last_timestep = matched_step

    current_user.totp_enabled = True
    current_user.totp_verified_at = datetime.utcnow()

    # Issue recovery codes. Plaintext is in `codes`; only the bcrypt
    # hashes are persisted. GHSA-vm6w-9wm5-q367 follow-up.
    from auth.recovery_codes import generate_codes, hash_code
    from models.recovery_code import RecoveryCode
    codes = generate_codes()
    for plaintext in codes:
        db.add(RecoveryCode(user_id=current_user.id, code_hash=hash_code(plaintext)))
    await db.commit()

    try:
        from utils.collaboration import create_activity_log
        await create_activity_log(
            db,
            engagement_id=None,
            user_id=current_user.id,
            action="issued_recovery_codes",
            resource_type="user",
            resource_id=current_user.id,
            resource_name=current_user.username,
            details=f"Issued {len(codes)} 2FA recovery codes at enrollment",
        )
    except Exception:
        pass  # audit best-effort; don't block the 2FA-enable

    # MFA boundary changed: invalidate every existing session and
    # long-lived API token so a stolen pre-2FA bearer cannot survive
    # the user enabling 2FA (mirrors the password-change path).
    from auth.jwt import revoke_all_user_tokens
    from sqlalchemy import update as _sa_update
    from models.api_token import ApiToken
    if not revoke_all_user_tokens(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Session revocation failed. Please retry.",
        )
    await db.execute(
        _sa_update(ApiToken)
        .where(ApiToken.user_id == current_user.id)
        .values(is_active=False)
    )
    await db.commit()

    return TotpVerifySetupResponse(
        message="Two-factor authentication enabled successfully",
        recovery_codes=codes,
    )


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
    matched_step = verify_totp_code(
        decrypted_secret, body.code, current_user.totp_last_timestep
    )
    if matched_step is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or already-used TOTP code",
        )
    current_user.totp_last_timestep = matched_step

    current_user.totp_secret = None
    current_user.totp_enabled = False
    current_user.totp_verified_at = None

    # Clear recovery codes — disabling 2FA invalidates the entire
    # second-factor surface. Re-enabling later issues a fresh batch.
    # GHSA-vm6w-9wm5-q367 follow-up.
    from sqlalchemy import delete as _sa_delete
    from models.recovery_code import RecoveryCode
    await db.execute(
        _sa_delete(RecoveryCode).where(RecoveryCode.user_id == current_user.id)
    )
    await db.commit()

    try:
        from utils.collaboration import create_activity_log
        await create_activity_log(
            db,
            engagement_id=None,
            user_id=current_user.id,
            action="cleared_recovery_codes",
            resource_type="user",
            resource_id=current_user.id,
            resource_name=current_user.username,
            details="Recovery codes cleared on 2FA disable",
        )
    except Exception:
        pass

    # MFA boundary changed: invalidate every existing session and
    # long-lived API token so a stolen post-2FA bearer cannot survive
    # the user disabling 2FA (mirrors the password-change path).
    from auth.jwt import revoke_all_user_tokens
    from sqlalchemy import update as _sa_update
    from models.api_token import ApiToken
    if not revoke_all_user_tokens(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Session revocation failed. Please retry.",
        )
    await db.execute(
        _sa_update(ApiToken)
        .where(ApiToken.user_id == current_user.id)
        .values(is_active=False)
    )
    await db.commit()

    return {"message": "Two-factor authentication disabled successfully"}


@router.post(
    "/totp/recovery-codes/regenerate",
    response_model=RecoveryCodesResponse,
    summary="Regenerate 2FA recovery codes",
    description="Deletes the user's existing recovery-code set and issues "
                "10 fresh codes. Requires the current password AND a valid "
                "TOTP code — re-issuance is a credential-class event, same "
                "shape as /totp/disable. Plaintext codes are returned ONCE "
                "in this response and never recoverable afterwards.",
)
@limiter.limit("5/minute")
async def regenerate_recovery_codes(
    request: Request,
    body: RecoveryCodesRegenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Regenerate recovery codes for a user with 2FA enabled."""
    if not current_user.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Two-factor authentication is not enabled",
        )

    if not verify_password(body.password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password",
        )

    from auth.crypto import decrypt_totp_secret
    decrypted_secret = decrypt_totp_secret(current_user.totp_secret)
    matched_step = verify_totp_code(
        decrypted_secret, body.code, current_user.totp_last_timestep
    )
    if matched_step is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or already-used TOTP code",
        )
    current_user.totp_last_timestep = matched_step

    from sqlalchemy import delete as _sa_delete
    from auth.recovery_codes import generate_codes, hash_code
    from models.recovery_code import RecoveryCode

    # Clear ALL existing rows for this user (used + unused). After this
    # call, only the freshly-issued codes are valid.
    await db.execute(
        _sa_delete(RecoveryCode).where(RecoveryCode.user_id == current_user.id)
    )

    codes = generate_codes()
    for plaintext in codes:
        db.add(RecoveryCode(user_id=current_user.id, code_hash=hash_code(plaintext)))
    await db.commit()

    try:
        from utils.collaboration import create_activity_log
        await create_activity_log(
            db,
            engagement_id=None,
            user_id=current_user.id,
            action="regenerated_recovery_codes",
            resource_type="user",
            resource_id=current_user.id,
            resource_name=current_user.username,
            details=f"Regenerated {len(codes)} 2FA recovery codes",
        )
    except Exception:
        pass

    return RecoveryCodesResponse(recovery_codes=codes)


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
        "want_messages_signed": cfg.get("saml_want_messages_signed", "false"),
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
        "want_messages_signed": cfg.get("saml_want_messages_signed", "false"),
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
    name_id = (user_info.get("name_id") or "").strip()

    if not email:
        raise HTTPException(status_code=400, detail="No email in SAML assertion")

    # GHSA-68hx-hggg-vrr2 follow-up: SAML's documented identity is the
    # NameID, not the email. Refuse the assertion if NameID is missing
    # — the previous code fell back to email-only matching which means
    # an IdP-side email rotation orphans the RedWire row, and any
    # email-collision attack on the IdP side flows straight through.
    if not name_id:
        logger.error("SAML ACS: assertion is missing NameID — refusing")
        raise HTTPException(
            status_code=400,
            detail="SAML assertion is missing a NameID",
        )

    # Match by saml_subject first — the IdP-stable identifier. An IdP
    # email rotation no longer orphans the row because we don't key on
    # email at all for returning users.
    result = await db.execute(select(User).where(User.saml_subject == name_id))
    user = result.scalar_one_or_none()

    if user is None:
        # No saml_subject match. Two cases:
        #   (a) Brand-new user — JIT provision below.
        #   (b) Existing SAML user provisioned BEFORE this commit landed
        #       (saml_subject is NULL). Backfill on first post-rollout
        #       login by matching on email + auth_provider="saml" +
        #       saml_subject IS NULL.
        legacy_result = await db.execute(
            select(User).where(
                User.email == email,
                User.auth_provider == "saml",
                User.saml_subject.is_(None),
            )
        )
        legacy_user = legacy_result.scalar_one_or_none()
        if legacy_user is not None:
            legacy_user.saml_subject = name_id
            user = legacy_user
            logger.info(
                "SAML ACS: backfilled saml_subject for legacy user %r",
                user.username,
            )

    if user is None:
        # Still no match by saml_subject OR by legacy-email-fallback.
        # Check the email-collision guard against non-SAML rows before
        # JIT-provisioning, same as before.
        collision = await db.execute(select(User).where(User.email == email))
        existing = collision.scalar_one_or_none()
        if existing and (existing.auth_provider or "local") != "saml":
            logger.warning(
                "SAML ACS: assertion email %r collides with existing "
                "auth_provider=%r user — refusing",
                email, existing.auth_provider,
            )
            raise HTTPException(
                status_code=403,
                detail="A non-SAML account already exists for this email",
            )
        if existing and (existing.auth_provider or "local") == "saml":
            # A SAML row with this email exists but its saml_subject is
            # a *different* value — that means the IdP issued a NameID
            # change for a user whose email also changed. Two distinct
            # SAML subjects sharing one email shouldn't be silently
            # merged; refuse and let the admin resolve.
            logger.warning(
                "SAML ACS: assertion NameID %r and email %r conflict "
                "with existing SAML row whose saml_subject=%r — refusing",
                name_id, email, existing.saml_subject,
            )
            raise HTTPException(
                status_code=403,
                detail="A different SAML identity already owns this email",
            )

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
            saml_subject=name_id,
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

    # Sync IdP-mutable attributes on every successful auth so an
    # IdP-side rename / email rotation reflects in the local row.
    # We key on saml_subject now, so the email is descriptive
    # metadata — not the identity. GHSA-68hx-hggg-vrr2 follow-up.
    if user.auth_provider == "saml":
        if email and user.email != email:
            user.email = email
        full_name = user_info.get("full_name") or ""
        if full_name and user.full_name != full_name:
            user.full_name = full_name

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
        "want_messages_signed": cfg.get("saml_want_messages_signed", "false"),
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


async def _dispatch_reset_email(to_email: str, reset_url: str, username: str) -> None:
    """Background-task helper that actually sends the password reset email.

    Opens its own AsyncSessionLocal() because the request's Depends(get_db)
    session is closed before FastAPI runs background tasks. Exceptions are
    logged here rather than raised — a SMTP failure must not be observable
    to the caller (would re-introduce the enumeration timing oracle).
    GHSA-rrrx-36ww-rq4q.
    """
    from utils.email_service import send_password_reset_email
    try:
        async with AsyncSessionLocal() as bg_db:
            await send_password_reset_email(bg_db, to_email, reset_url, username)
    except Exception as e:
        logger.error(f"Failed to send reset email to {to_email}: {e}")


@router.post(
    "/forgot-password",
    summary="Request password reset email",
    description="Public endpoint — sends a password reset email if the email exists. "
                "Always returns 200 to prevent user enumeration.",
)
@limiter.limit("5/minute")
async def forgot_password(
    request: Request,
    req: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Generate a reset token and schedule the password reset email.

    The dispatch is moved off the request path (GHSA-rrrx-36ww-rq4q) so
    response time is constant whether or not the email matched — closing
    the account-existence timing oracle.
    """
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

        background_tasks.add_task(
            _dispatch_reset_email, user.email, reset_url, user.username,
        )

    return {"message": "If an account with that email exists, a password reset link has been sent."}


@router.post(
    "/reset-password",
    summary="Reset password with token",
    description="Public endpoint — resets the user's password using a valid reset token.",
)
@limiter.limit("5/minute")
async def reset_password(
    request: Request,
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
    
    # Blacklist the reset token so it cannot be replayed, then revoke
    # all existing sessions. Both must surface failure instead of silently
    # no-op. GHSA-832g-v288-v593.
    from auth.jwt import blacklist_token, revoke_all_user_tokens
    if not blacklist_token(req.token):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Session revocation failed. Please retry.",
        )
    if not revoke_all_user_tokens(user.id):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Session revocation failed. Please retry.",
        )

    logger.info(f"Password reset completed for user {user.username}")
    return {"message": "Password has been reset successfully. You can now log in with your new password."}
