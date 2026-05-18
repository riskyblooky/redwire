"""
API Token endpoints.

User endpoints:
  GET    /api-tokens       — list own tokens
  POST   /api-tokens       — create a token (returns raw value once)
  DELETE /api-tokens/{id}  — revoke own token

Admin endpoints:
  GET    /admin/api-tokens       — list all tokens
  POST   /admin/api-tokens       — create token for any user
  DELETE /admin/api-tokens/{id}  — revoke any token
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db
from models.user import User, UserRole
from models.api_token import ApiToken
from schemas.api_token import (
    ApiTokenCreate, ApiTokenAdminCreate,
    ApiTokenResponse, ApiTokenCreated, ApiTokenAdminResponse,
)
from auth.dependencies import get_current_user
from datetime import datetime
import uuid
import hashlib
import secrets
import logging

logger = logging.getLogger(__name__)

router = APIRouter(tags=["api-tokens"])


def _generate_token(permission: str) -> tuple[str, str, str]:
    """Generate a raw token, its hash, and prefix.

    Format: {permission}_{40 hex chars}
    Returns: (raw_token, token_hash, token_prefix)
    """
    random_part = secrets.token_hex(20)  # 40 hex chars
    raw_token = f"{permission}_{random_part}"
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    token_prefix = raw_token[:12]  # e.g. "rw_a1b2c3d4e"
    return raw_token, token_hash, token_prefix


# ─── User endpoints ──────────────────────────────────────────────────────────

@router.get(
    "/api-tokens",
    response_model=list[ApiTokenResponse],
    summary="List own API tokens",
    description="Returns all API tokens belonging to the current user.",
)
async def list_own_tokens(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List the current user's API tokens."""
    result = await db.execute(
        select(ApiToken)
        .where(ApiToken.user_id == current_user.id)
        .order_by(ApiToken.created_at.desc())
    )
    return result.scalars().all()


@router.post(
    "/api-tokens",
    response_model=ApiTokenCreated,
    status_code=status.HTTP_201_CREATED,
    summary="Create API token",
    description="Generates a new API token. The raw token is returned once in the response — store it securely.",
)
async def create_own_token(
    body: ApiTokenCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new API token for the current user. Raw token is returned once.

    Minting is a credential-issuance event, so for local-auth users we
    require the current password (and TOTP if enabled) before issuing the
    token — same step-up the password-change path already enforces. A
    stolen session bearer alone is not sufficient to mint a long-lived
    API token (GHSA-7rcx-8hqc-mm5f). SSO/LDAP users have no local
    hashed_password to verify against and currently skip this step-up;
    session-freshness-based step-up for them is tracked as a follow-up.
    """
    if current_user.auth_provider == "local":
        from auth.password import verify_password
        if not body.password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password is required to mint an API token.",
            )
        if not verify_password(body.password, current_user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect password",
            )
        if current_user.totp_enabled and current_user.totp_secret:
            from auth.totp import verify_totp_code
            from auth.crypto import decrypt_totp_secret
            if not body.totp_code:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Two-factor authentication code required.",
                )
            decrypted_secret = decrypt_totp_secret(current_user.totp_secret)
            if not verify_totp_code(decrypted_secret, body.totp_code):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid two-factor authentication code.",
                )

    raw_token, token_hash, token_prefix = _generate_token(body.permission)

    # Strip timezone info if present (DB uses naive timestamps)
    expires = body.expires_at.replace(tzinfo=None) if body.expires_at else None

    token = ApiToken(
        id=str(uuid.uuid4()),
        name=body.name,
        token_hash=token_hash,
        token_prefix=token_prefix,
        permission=body.permission,
        user_id=current_user.id,
        expires_at=expires,
        created_by=current_user.id,
        created_at=datetime.utcnow(),
        is_active=True,
    )
    db.add(token)
    await db.commit()
    await db.refresh(token)

    logger.info(f"API token created: {token_prefix}... for user {current_user.username}")

    return ApiTokenCreated(
        id=token.id,
        name=token.name,
        token_prefix=token.token_prefix,
        permission=token.permission,
        user_id=token.user_id,
        created_at=token.created_at,
        last_used_at=token.last_used_at,
        expires_at=token.expires_at,
        is_active=token.is_active,
        created_by=token.created_by,
        raw_token=raw_token,
    )


@router.delete(
    "/api-tokens/{token_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke own API token",
    description="Deactivates one of the current user's API tokens. The token becomes immediately unusable.",
)
async def revoke_own_token(
    token_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke one of the current user's API tokens."""
    result = await db.execute(
        select(ApiToken).where(ApiToken.id == token_id, ApiToken.user_id == current_user.id)
    )
    token = result.scalar_one_or_none()
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")

    token.is_active = False
    await db.commit()


# ─── Admin endpoints ─────────────────────────────────────────────────────────

@router.get(
    "/admin/api-tokens",
    response_model=list[ApiTokenAdminResponse],
    summary="List all API tokens (admin)",
    description="Returns every API token across all users. Includes username and full name for each token owner.",
)
async def admin_list_tokens(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all API tokens (admin only)."""
    if current_user.role.value not in [UserRole.ADMIN.value, UserRole.READ_ONLY_ADMIN.value]:
        raise HTTPException(status_code=403, detail="Admin access required")

    result = await db.execute(
        select(ApiToken, User.username, User.full_name)
        .join(User, ApiToken.user_id == User.id)
        .order_by(ApiToken.created_at.desc())
    )
    rows = result.all()

    return [
        ApiTokenAdminResponse(
            id=token.id,
            name=token.name,
            token_prefix=token.token_prefix,
            permission=token.permission,
            user_id=token.user_id,
            created_at=token.created_at,
            last_used_at=token.last_used_at,
            expires_at=token.expires_at,
            is_active=token.is_active,
            created_by=token.created_by,
            username=username,
            user_full_name=full_name,
        )
        for token, username, full_name in rows
    ]


@router.post(
    "/admin/api-tokens",
    response_model=ApiTokenCreated,
    status_code=status.HTTP_201_CREATED,
    summary="Create service token (admin)",
    description="Generates an API token for any user. Useful for creating service account tokens.",
)
async def admin_create_token(
    body: ApiTokenAdminCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create an API token for any user (admin only). Used for service tokens."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Full admin access required")

    # Verify target user exists
    target = await db.execute(select(User).where(User.id == body.user_id))
    target_user = target.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404, detail="Target user not found")

    raw_token, token_hash, token_prefix = _generate_token(body.permission)

    # Strip timezone info if present (DB uses naive timestamps)
    expires = body.expires_at.replace(tzinfo=None) if body.expires_at else None

    token = ApiToken(
        id=str(uuid.uuid4()),
        name=body.name,
        token_hash=token_hash,
        token_prefix=token_prefix,
        permission=body.permission,
        user_id=body.user_id,
        expires_at=expires,
        created_by=current_user.id,
        created_at=datetime.utcnow(),
        is_active=True,
    )
    db.add(token)
    await db.commit()
    await db.refresh(token)

    logger.info(
        f"Admin {current_user.username} created API token {token_prefix}... for user {target_user.username}"
    )

    return ApiTokenCreated(
        id=token.id,
        name=token.name,
        token_prefix=token.token_prefix,
        permission=token.permission,
        user_id=token.user_id,
        created_at=token.created_at,
        last_used_at=token.last_used_at,
        expires_at=token.expires_at,
        is_active=token.is_active,
        created_by=token.created_by,
        raw_token=raw_token,
    )


@router.delete(
    "/admin/api-tokens/{token_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke any API token (admin)",
    description="Deactivates any API token regardless of owner.",
)
async def admin_revoke_token(
    token_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke any API token (admin only)."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Full admin access required")

    result = await db.execute(select(ApiToken).where(ApiToken.id == token_id))
    token = result.scalar_one_or_none()
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")

    token.is_active = False
    await db.commit()
