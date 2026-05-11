from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from database import get_db
from models.user import User, UserRole
from auth.jwt import decode_token, is_token_blacklisted
from typing import Optional
import hashlib
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# ── Role group constants ──────────────────────────────────────────────────
# Use these instead of hardcoding role lists in every router.
ADMIN_ROLES = [UserRole.ADMIN.value, UserRole.READ_ONLY_ADMIN.value]
WRITE_ADMIN_ROLES = [UserRole.ADMIN.value]
PRIVILEGED_ROLES = [UserRole.ADMIN.value, UserRole.READ_ONLY_ADMIN.value, UserRole.TEAM_LEAD.value]

security = HTTPBearer()


def _is_api_token(raw: str) -> bool:
    """Check if a bearer value looks like an API token (ro_ or rw_ prefix)."""
    return raw.startswith("ro_") or raw.startswith("rw_")


async def _resolve_api_token(raw: str, db: AsyncSession) -> tuple[User, str]:
    """Look up an API token by its hash and return (user, permission).

    Raises HTTPException on any failure.
    """
    from models.api_token import ApiToken

    token_hash = hashlib.sha256(raw.encode()).hexdigest()

    result = await db.execute(
        select(ApiToken)
        .where(ApiToken.token_hash == token_hash)
        .options()
    )
    api_token = result.scalar_one_or_none()

    if api_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not api_token.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API token has been revoked",
        )

    if api_token.expires_at and api_token.expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API token has expired",
        )

    # Update last_used_at (fire-and-forget; don't fail the request)
    try:
        api_token.last_used_at = datetime.utcnow()
        await db.commit()
    except Exception:
        await db.rollback()

    # Load the owning user
    user_result = await db.execute(
        select(User)
        .where(User.id == api_token.user_id)
        .options(selectinload(User.groups))
    )
    user = user_result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token owner not found or inactive",
        )

    return user, api_token.permission


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Get the current authenticated user from a JWT or API token."""
    token = credentials.credentials

    # ── API token path ────────────────────────────────────────────────────
    if _is_api_token(token):
        user, permission = await _resolve_api_token(token, db)
        request.state.api_token_permission = permission

        # Enforce read-only: reject mutating HTTP methods
        if permission == "ro" and request.method in ("POST", "PUT", "PATCH", "DELETE"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This API token is read-only",
            )

        return user

    # ── JWT path (existing) ───────────────────────────────────────────────
    request.state.api_token_permission = None  # full access via JWT

    # Check if token has been revoked
    if is_token_blacklisted(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Decode token
    payload = decode_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check token type
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    # Reject 2FA-pending tokens — they must only be used at /auth/verify-2fa
    if payload.get("2fa_pending"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Two-factor authentication required",
        )

    # Get user from database
    user_id: str = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )

    result = await db.execute(
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.groups))
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Get current active user (alias for consistency)."""
    return current_user


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
    db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    """Get current user if authenticated, None otherwise."""
    if credentials is None:
        return None

    try:
        token = credentials.credentials

        # Reject revoked tokens
        if is_token_blacklisted(token):
            return None

        payload = decode_token(token)
        if payload is None:
            return None

        # Reject 2FA-pending tokens
        if payload.get("2fa_pending"):
            return None

        user_id = payload.get("sub")
        if user_id is None:
            return None

        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        return user if user and user.is_active else None
    except Exception as e:
        logger.debug(f"Optional auth failed: {e}")
        return None


def require_roles(allowed_roles: list[str]):
    """Dependency factory for checking user roles."""
    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role.value not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operation not permitted for your role"
            )
        return current_user
    return role_checker


async def require_write(request: Request):
    """Dependency that rejects read-only API tokens.

    Add this as a dependency to any endpoint that mutates data, e.g.:
        @router.post("/items", dependencies=[Depends(require_write)])
    """
    perm = getattr(request.state, "api_token_permission", None)
    if perm == "ro":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This API token is read-only",
        )

