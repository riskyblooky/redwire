import logging
from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Query
from schemas._field_limits import MAX_LIST_LIMIT
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import List
from database import get_db
from models.user import User, UserRole
from schemas.user import UserResponse, UserSummary, UserCreate, UserUpdate, UserPasswordUpdate, ALLOWED_THEMES, ALLOWED_PALETTES
from auth.dependencies import get_current_user
from auth.password import get_password_hash
from utils.paths import ensure_within
from utils.uploads import read_upload_capped

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/users", tags=["users"])


# GHSA-h77m-pjqc-5cm3: profile-photo upload hardening.
# Allow-list, size cap, and magic-byte sniff so a client can never
# land an executable extension or HTML body in uploads/profile_photos.
import os as _h77m_os

_PROFILE_PHOTO_MAX_BYTES = int(
    _h77m_os.getenv("PROFILE_PHOTO_MAX_BYTES", str(5 * 1024 * 1024))
)
_ALLOWED_PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


def _sniff_image_ext(head: bytes) -> "str | None":
    """Return a canonical image extension (with leading dot) if ``head``
    starts with a known image signature. None otherwise.
    """
    if not head:
        return None
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if head.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if head.startswith(b"GIF87a") or head.startswith(b"GIF89a"):
        return ".gif"
    # WebP: 'RIFF' .... 'WEBP'
    if len(head) >= 12 and head[0:4] == b"RIFF" and head[8:12] == b"WEBP":
        return ".webp"
    return None

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """Get current user information."""
    return current_user

@router.get("/me/permissions")
async def get_my_global_permissions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get current user's global permissions from group memberships."""
    from models.permission import Permission, GroupPermissions, GLOBAL_PERMISSIONS
    from models.group import Group, user_groups

    # Admins get all global permissions
    if current_user.role == UserRole.ADMIN:
        return [p.value for p in GLOBAL_PERMISSIONS]

    # Query all groups the user belongs to
    query = (
        select(GroupPermissions.permissions)
        .join(Group, GroupPermissions.group_id == Group.id)
        .join(user_groups, Group.id == user_groups.c.group_id)
        .where(user_groups.c.user_id == current_user.id)
    )
    result = await db.execute(query)
    all_group_permissions = result.scalars().all()

    permissions_set = set()
    for group_perms in all_group_permissions:
        if group_perms:
            permissions_set.update(group_perms)

    # Only return global permissions (filter out any engagement-scoped ones)
    global_values = {p.value for p in GLOBAL_PERMISSIONS}
    return sorted(permissions_set & global_values)

@router.put("/me", response_model=UserResponse)
async def update_current_user(
    user_data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update current user profile information."""
    # Email is the password-reset identity (POST /auth/forgot-password
    # mails the reset link to this address). Changing it with only a
    # bearer token converts a stolen session into permanent account
    # takeover (GHSA-hc9w-hggj-r52w). Require the current password and,
    # if 2FA is enrolled, a TOTP code — mirroring PUT /me/password.
    email_changing = bool(user_data.email and user_data.email != current_user.email)
    if email_changing:
        # SSO/LDAP accounts authenticate via the IdP and have no
        # local hashed_password to verify against — and the IdP is
        # the owner of that attribute anyway.
        if current_user.auth_provider != "local":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Email is managed by your identity provider.",
            )
        from auth.password import verify_password
        if not user_data.current_password or not verify_password(
            user_data.current_password, current_user.hashed_password
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Current password required to change email.",
            )
        if current_user.totp_enabled and current_user.totp_secret:
            from auth.totp import verify_totp_code
            from auth.crypto import decrypt_totp_secret
            if not user_data.totp_code:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Two-factor authentication code required.",
                )
            decrypted_secret = decrypt_totp_secret(current_user.totp_secret)
            matched_step = verify_totp_code(
                decrypted_secret, user_data.totp_code, current_user.totp_last_timestep
            )
            if matched_step is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or already-used two-factor authentication code.",
                )
            current_user.totp_last_timestep = matched_step
        result = await db.execute(select(User).where(User.email == user_data.email))
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )

    # Update fields (excluding role and is_active which are admin-only in UserUpdate).
    # current_password / totp_code are step-up inputs, never persisted.
    update_data = user_data.model_dump(
        exclude_unset=True,
        exclude={"current_password", "totp_code"},
    )

    # `profile_photo` is intentionally excluded — it is server-set by
    # POST /users/me/photo. Allowing self-service writes here would
    # turn the upload handler's pre-delete into an arbitrary-path
    # os.remove primitive.
    allowed_fields = {"email", "full_name", "theme_preference", "theme_palette", "theme_accent_custom"}
    if "theme_preference" in update_data:
        if update_data["theme_preference"] not in ALLOWED_THEMES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid theme. Allowed: {sorted(ALLOWED_THEMES)}",
            )
    if "theme_palette" in update_data:
        if update_data["theme_palette"] not in ALLOWED_PALETTES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid palette. Allowed: {sorted(ALLOWED_PALETTES)}",
            )
    if "theme_accent_custom" in update_data:
        v = update_data["theme_accent_custom"]
        if v is not None and v != "":
            import re
            if not re.fullmatch(r"#[0-9a-fA-F]{6}", v):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid custom color. Must be hex like #a855f7.",
                )
        else:
            update_data["theme_accent_custom"] = None
    for field, value in update_data.items():
        if field in allowed_fields:
            setattr(current_user, field, value)

    await db.commit()
    await db.refresh(current_user)

    if email_changing:
        # Treat email change as a credential change — invalidate all
        # outstanding sessions and long-lived API tokens so any other
        # stolen bearer can't keep the attacker in (mirrors the
        # /me/password path; GHSA-hc9w-hggj-r52w).
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

    return current_user

@router.put("/me/password", status_code=status.HTTP_200_OK)
async def change_password(
    password_data: UserPasswordUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Change current user password.

    If 2FA is enabled on the account, a valid TOTP code must accompany the
    request — preventing a stolen session token from being used to lock the
    real owner out. On success, all existing sessions for the user are
    revoked so the caller (and any other live session) must re-authenticate.
    """
    from auth.password import verify_password
    from auth.totp import verify_totp_code
    from auth.crypto import decrypt_totp_secret
    from auth.jwt import revoke_all_user_tokens

    if not verify_password(password_data.old_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect old password"
        )

    if current_user.totp_enabled and current_user.totp_secret:
        if not password_data.totp_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Two-factor authentication code required",
            )
        decrypted_secret = decrypt_totp_secret(current_user.totp_secret)
        matched_step = verify_totp_code(
            decrypted_secret, password_data.totp_code, current_user.totp_last_timestep
        )
        if matched_step is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or already-used two-factor authentication code",
            )
        current_user.totp_last_timestep = matched_step

    current_user.hashed_password = get_password_hash(password_data.new_password)
    await db.commit()

    if not revoke_all_user_tokens(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Session revocation failed. Please retry.",
        )

    return {"detail": "Password updated successfully"}

@router.post("/me/photo", response_model=UserResponse)
async def upload_profile_photo(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Upload profile photo. GHSA-h77m-pjqc-5cm3: allow-list + magic-byte
    sniff + size cap; the stored extension comes from the sniffed image
    signature, never from the client-supplied filename.
    """
    import os
    import uuid

    # GHSA-h77m: reject any extension outside the image allow-list before
    # we read a byte of the body.
    claimed_ext = os.path.splitext(file.filename or "")[1].lower()
    if claimed_ext not in _ALLOWED_PHOTO_EXTS:
        logger.warning(
            "Refused profile photo upload from user %s: extension %r not in allow-list",
            current_user.id, claimed_ext,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Profile photo must be an image: "
                f"{', '.join(sorted(_ALLOWED_PHOTO_EXTS))}."
            ),
        )

    content = await read_upload_capped(
        file, _PROFILE_PHOTO_MAX_BYTES,
        detail=f"Profile photo exceeds the {_PROFILE_PHOTO_MAX_BYTES}-byte size limit.",
    )

    # GHSA-h77m: confirm the body actually IS an image; reject otherwise.
    # The stored extension comes from the sniff, not the client's claim,
    # so a renamed .html → .png never lands as .png on disk.
    sniffed_ext = _sniff_image_ext(content[:16])
    if sniffed_ext is None:
        logger.warning(
            "Refused profile photo upload from user %s: content is not a recognized image",
            current_user.id,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Profile photo content is not a recognized image (PNG/JPEG/GIF/WebP).",
        )

    # Create uploads directory if it doesn't exist
    upload_dir = "uploads/profile_photos"
    os.makedirs(upload_dir, exist_ok=True)

    # Generate unique filename — sniffed extension, not the client's claim.
    filename = f"{current_user.id}_{uuid.uuid4()}{sniffed_ext}"
    file_path = os.path.join(upload_dir, filename)

    # Save file
    with open(file_path, "wb") as f:
        f.write(content)
    
    # Delete old photo if it exists *and* resolves inside the uploads tree.
    # A non-conforming value means either pre-patch corruption or a
    # bypass attempt; log and skip rather than honouring it.
    if current_user.profile_photo and os.path.exists(current_user.profile_photo):
        if ensure_within(current_user.profile_photo, upload_dir):
            try:
                os.remove(current_user.profile_photo)
            except Exception as e:
                logger.warning("Error removing old profile photo: %s", e)
        else:
            logger.warning(
                "Refusing to remove profile photo path outside upload dir: %s",
                current_user.profile_photo,
            )

    # Update user record
    current_user.profile_photo = file_path
    await db.commit()
    await db.refresh(current_user)
    
    return current_user

@router.get("", response_model=List[UserSummary])
async def get_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    skip: int = 0,
    limit: int = Query(100, ge=1, le=MAX_LIST_LIMIT)
):
    """Team picker — returns lightweight UserSummary rows visible to any
    authenticated user. The full UserResponse (with auth_provider,
    totp_enabled, last_login etc.) is reserved for /api/admin/users
    (GHSA-52gv-wf4c-7qmm).

    Filters to `is_active=True` at the query level so disabled accounts
    don't clutter the team-assignment picker. The frontend used to
    filter client-side but the switch to UserSummary (which
    intentionally omits is_active) turned that filter into a no-op
    that dropped every row.
    """
    result = await db.execute(
        select(User)
        .where(User.is_active == True)
        .offset(skip).limit(limit)
    )
    return result.scalars().all()

@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific user by ID (Admin only)."""
    if current_user.role != UserRole.ADMIN and current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions"
        )
    
    result = await db.execute(
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.groups))
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return user

@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new user (Admin only)."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can create users"
        )
    
    # Check if username/email already exists
    result = await db.execute(
        select(User).where((User.username == user_data.username) | (User.email == user_data.email))
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already registered"
        )
    
    new_user = User(
        username=user_data.username,
        email=user_data.email,
        full_name=user_data.full_name,
        role=user_data.role,
        hashed_password=get_password_hash(user_data.password)
    )
    
    db.add(new_user)
    await db.flush()
    
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

    # Lifecycle hook — plugins can subscribe for provisioning
    # (Slack invite, LDAP mirror, welcome email). Fired after commit
    # so subscribers can safely re-fetch the user. Password hash and
    # any secrets are deliberately omitted from the payload.
    try:
        from utils.event_bus import event_bus
        await event_bus.emit("user.created", {
            "resource_id": new_user.id,
            "resource_type": "user",
            "user_id": new_user.id,
            "username": new_user.username,
            "email": new_user.email,
            "full_name": new_user.full_name,
            "role": new_user.role.value if new_user.role else None,
            "actor_id": current_user.id,
        })
    except Exception as _e:
        print(f"[users] user.created event emit error (non-fatal): {_e}")

    # Re-fetch with groups loaded
    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(User)
        .where(User.id == new_user.id)
        .options(selectinload(User.groups))
    )
    new_user = result.scalar_one()
    
    return new_user

@router.put("/{user_id}", response_model=UserResponse)

async def update_user(
    user_id: str,
    user_data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a user (Admin only)."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can update users"
        )
    
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Update fields
    update_data = user_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(user, field, value)
    
    await db.commit()
    await db.refresh(user)
    
    return user

@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a user (Admin only)."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can delete users"
        )
    
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account"
        )
    
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    await db.delete(user)
    await db.commit()
    
    return None
