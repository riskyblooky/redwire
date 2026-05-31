from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import List

from database import get_db
from models.user import User, UserRole
from models.group import Group
from models.engagement_role import EngagementRole
from schemas.user import UserResponse, UserUpdate
from schemas.rbac import (
    GroupResponse, GroupCreate, GroupUpdate,
    EngagementRoleResponse, EngagementRoleCreate, EngagementRoleUpdate
)
from auth.dependencies import get_current_user, require_roles, ADMIN_ROLES, WRITE_ADMIN_ROLES

router = APIRouter(
    prefix="/admin",
    tags=["admin"]
)

from pydantic import BaseModel, field_validator
from typing import Optional

class AdminUserCreate(BaseModel):
    username: str
    email: str
    password: str
    full_name: Optional[str] = ""
    role: UserRole = UserRole.OPERATOR

    @field_validator("username")
    @classmethod
    def username_no_spaces(cls, v: str) -> str:
        if " " in v:
            raise ValueError("Username cannot contain spaces")
        return v.lower()


@router.get("/config")
async def get_admin_config(
    current_user: User = Depends(get_current_user)
):
    """Return platform config values needed by the admin UI."""
    from auth.jwt import REFRESH_TOKEN_EXPIRE_HOURS
    return {
        "session_timeout_hours": REFRESH_TOKEN_EXPIRE_HOURS,
    }

@router.get("/users", response_model=List[UserResponse], dependencies=[Depends(require_roles(WRITE_ADMIN_ROLES))])
async def list_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all users in the system (admin-only — full UserResponse with
    auth_provider, totp_enabled, last_login, etc.). The lightweight team
    picker lives at /api/users (GHSA-52gv-wf4c-7qmm)."""
    result = await db.execute(select(User).options(selectinload(User.groups)).order_by(User.created_at.desc()))
    users = result.scalars().all()
    return users

@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_roles(WRITE_ADMIN_ROLES))])
async def create_local_user(
    user_data: "AdminUserCreate",
    db: AsyncSession = Depends(get_db),
):
    """Create a local user account directly (admin-only). Bypasses invite codes."""
    from auth import get_password_hash
    from models.group import Group, user_groups

    # Check username/email uniqueness
    existing = await db.execute(
        select(User).where(
            (User.username == user_data.username) | (User.email == user_data.email)
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already in use",
        )

    new_user = User(
        username=user_data.username,
        email=user_data.email,
        full_name=user_data.full_name or "",
        role=user_data.role,
        hashed_password=get_password_hash(user_data.password),
        is_active=True,
    )
    db.add(new_user)
    await db.flush()

    # Auto-assign to default group
    default_group_result = await db.execute(select(Group).where(Group.is_default == True))
    default_group = default_group_result.scalar_one_or_none()
    if default_group:
        await db.execute(
            user_groups.insert().values(user_id=new_user.id, group_id=default_group.id)
        )

    await db.commit()

    result = await db.execute(
        select(User).where(User.id == new_user.id).options(selectinload(User.groups))
    )
    return result.scalar_one()


@router.patch("/users/{user_id}", response_model=UserResponse, dependencies=[Depends(require_roles(WRITE_ADMIN_ROLES))])
async def update_user(
    user_id: str,
    user_update: UserUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update a user's role, status, or group memberships."""
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
        
    update_data = user_update.model_dump(exclude={'group_ids'}, exclude_unset=True)
    for key, value in update_data.items():
        setattr(user, key, value)
    
    if user_update.group_ids is not None:
        group_ids = user_update.group_ids
        if not group_ids:
            user.groups = []
        else:
            group_result = await db.execute(select(Group).where(Group.id.in_(group_ids)))
            user.groups = group_result.scalars().all()
        
    await db.commit()
    await db.refresh(user)
    return user

@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_roles(WRITE_ADMIN_ROLES))])
async def delete_user(
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a user account."""
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

@router.post("/users/{user_id}/reset-password", dependencies=[Depends(require_roles(WRITE_ADMIN_ROLES))])
async def reset_password(
    user_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Reset a user's password to a temporary one."""
    import secrets
    import string
    from auth import get_password_hash
    
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # SSO/LDAP-bound accounts authenticate against their IdP — planting
    # a hashed_password here would create a permanent IdP bypass for
    # them via the login path (GHSA-39x9-f79h-rh4r precondition).
    # Mirrors the existing guard at auth.py:894 on /auth/reset-password.
    if user.auth_provider != "local":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Cannot reset password for users authenticated via "
                f"{user.auth_provider.upper()}. They authenticate via "
                "their identity provider."
            ),
        )

    # Generate temporary password
    alphabet = string.ascii_letters + string.digits
    temp_password = ''.join(secrets.choice(alphabet) for i in range(12))
    
    # Update user's password and force them to change it on next login
    user.hashed_password = get_password_hash(temp_password)
    user.must_change_password = True
    await db.commit()
    
    # Revoke all existing sessions. Surface failure rather than silently
    # leaving the old session live after a "successful" admin reset.
    # GHSA-832g-v288-v593.
    from auth.jwt import revoke_all_user_tokens
    if not revoke_all_user_tokens(user.id):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Session revocation failed. Please retry.",
        )
    
    # Notify user that their password was reset
    from utils.collaboration import create_notification
    await create_notification(
        db=db,
        user_id=user_id,
        event_type="password_reset",
        title="Password Reset",
        message="An administrator has reset your password. You will need to change it on next login.",
        actor_id=None,
    )
    await db.commit()
    
    return {"temporary_password": temp_password}

# --- Group Management ---

@router.get("/groups", response_model=List[GroupResponse], dependencies=[Depends(require_roles(ADMIN_ROLES))])
async def list_groups(db: AsyncSession = Depends(get_db)):
    """List all user groups."""
    result = await db.execute(select(Group).order_by(Group.name))
    return result.scalars().all()

@router.post("/groups", response_model=GroupResponse, dependencies=[Depends(require_roles(WRITE_ADMIN_ROLES))])
async def create_group(group: GroupCreate, db: AsyncSession = Depends(get_db)):
    """Create a new user group."""
    new_group = Group(**group.model_dump())
    db.add(new_group)
    try:
        await db.commit()
        await db.refresh(new_group)
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Group name must be unique")
    return new_group

@router.patch("/groups/{group_id}", response_model=GroupResponse, dependencies=[Depends(require_roles(WRITE_ADMIN_ROLES))])
async def update_group(group_id: str, group_update: GroupUpdate, db: AsyncSession = Depends(get_db)):
    """Update a group's details."""
    result = await db.execute(select(Group).where(Group.id == group_id))
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    for key, value in group_update.model_dump(exclude_unset=True).items():
        setattr(group, key, value)
    
    await db.commit()
    await db.refresh(group)
    return group

@router.delete("/groups/{group_id}", status_code=204, dependencies=[Depends(require_roles(WRITE_ADMIN_ROLES))])
async def delete_group(group_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a user group."""
    result = await db.execute(select(Group).where(Group.id == group_id))
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    await db.delete(group)
    await db.commit()
    return None

# --- Engagement Role Management ---

@router.get("/engagement-roles", response_model=List[EngagementRoleResponse], dependencies=[Depends(require_roles(ADMIN_ROLES))])
async def list_engagement_roles(db: AsyncSession = Depends(get_db)):
    """List all defined engagement roles."""
    result = await db.execute(select(EngagementRole).order_by(EngagementRole.name))
    return result.scalars().all()

@router.post("/engagement-roles", response_model=EngagementRoleResponse, dependencies=[Depends(require_roles(WRITE_ADMIN_ROLES))])
async def create_engagement_role(role: EngagementRoleCreate, db: AsyncSession = Depends(get_db)):
    """Create a new engagement role."""
    new_role = EngagementRole(**role.model_dump())
    db.add(new_role)
    try:
        await db.commit()
        await db.refresh(new_role)
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Role name must be unique")
    return new_role

@router.patch("/engagement-roles/{role_id}", response_model=EngagementRoleResponse, dependencies=[Depends(require_roles(WRITE_ADMIN_ROLES))])
async def update_engagement_role(role_id: str, role_update: EngagementRoleUpdate, db: AsyncSession = Depends(get_db)):
    """Update an engagement role's details."""
    result = await db.execute(select(EngagementRole).where(EngagementRole.id == role_id))
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    for key, value in role_update.model_dump(exclude_unset=True).items():
        setattr(role, key, value)
    
    await db.commit()
    await db.refresh(role)
    return role

    await db.delete(role)
    await db.commit()
    return None

# --- Registration Code Management ---

from models.registration_code import RegistrationCode
from schemas.registration_code import RegistrationCodeCreate, RegistrationCodeUpdate, RegistrationCodeResponse, RegistrationCodeUserResponse
import uuid

@router.get("/registration-codes", response_model=List[RegistrationCodeResponse], dependencies=[Depends(require_roles(ADMIN_ROLES))])
async def list_registration_codes(db: AsyncSession = Depends(get_db)):
    """List all registration codes."""
    result = await db.execute(select(RegistrationCode).order_by(RegistrationCode.created_at.desc()))
    return result.scalars().all()

@router.post("/registration-codes", response_model=RegistrationCodeResponse, dependencies=[Depends(require_roles(WRITE_ADMIN_ROLES))])
async def create_registration_code(
    code_data: RegistrationCodeCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new registration code."""
    # Check uniqueness
    exists = await db.execute(select(RegistrationCode).where(RegistrationCode.code == code_data.code))
    if exists.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Code already exists")
        
    new_code = RegistrationCode(
        code=code_data.code,
        label=code_data.label,
        max_uses=code_data.max_uses,
        expires_at=code_data.expires_at,
        created_by=current_user.id
    )
    db.add(new_code)
    await db.commit()
    await db.refresh(new_code)
    return new_code

@router.patch("/registration-codes/{code_id}", response_model=RegistrationCodeResponse, dependencies=[Depends(require_roles(WRITE_ADMIN_ROLES))])
async def update_registration_code(
    code_id: str,
    code_update: RegistrationCodeUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update a registration code (toggle active, change max uses, etc)."""
    result = await db.execute(select(RegistrationCode).where(RegistrationCode.id == code_id))
    code = result.scalar_one_or_none()
    if not code:
        raise HTTPException(status_code=404, detail="Code not found")
    
    for key, value in code_update.model_dump(exclude_unset=True).items():
        setattr(code, key, value)
    
    await db.commit()
    await db.refresh(code)
    return code

@router.get("/registration-codes/{code_id}/users", response_model=List[RegistrationCodeUserResponse], dependencies=[Depends(require_roles(ADMIN_ROLES))])
async def get_registration_code_users(
    code_id: str,
    db: AsyncSession = Depends(get_db)
):
    """List users who registered with a specific code."""
    # Verify code exists
    code_result = await db.execute(select(RegistrationCode).where(RegistrationCode.id == code_id))
    if not code_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Code not found")
    
    result = await db.execute(
        select(User).where(User.registration_code_id == code_id).order_by(User.created_at.desc())
    )
    return result.scalars().all()

@router.delete("/registration-codes/{code_id}", status_code=204, dependencies=[Depends(require_roles(WRITE_ADMIN_ROLES))])
async def delete_registration_code(code_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a registration code."""
    result = await db.execute(select(RegistrationCode).where(RegistrationCode.id == code_id))
    code = result.scalar_one_or_none()
    if not code:
        raise HTTPException(status_code=404, detail="Code not found")
        
    await db.delete(code)
    await db.commit()
    return None


# ── Engagement Type Management (backed by configurable_types) ────

from models.configurable_type import ConfigurableType
from models.engagement import Engagement
from schemas.configurable_type import (
    ConfigurableTypeCreate, ConfigurableTypeUpdate, ConfigurableTypeResponse
)

engagement_type_router = APIRouter(prefix="/engagement-types", tags=["engagement-types"])

@engagement_type_router.get("", response_model=List[ConfigurableTypeResponse])
async def list_engagement_types(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all engagement types, ordered by sort_order."""
    result = await db.execute(
        select(ConfigurableType)
        .where(ConfigurableType.category == "engagement")
        .order_by(ConfigurableType.sort_order)
    )
    return result.scalars().all()

@engagement_type_router.post("", response_model=ConfigurableTypeResponse, status_code=status.HTTP_201_CREATED,
                              dependencies=[Depends(require_roles(WRITE_ADMIN_ROLES))])
async def create_engagement_type(
    data: ConfigurableTypeCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new engagement type."""
    # Get max sort_order
    max_result = await db.execute(
        select(sa.func.max(ConfigurableType.sort_order)).where(ConfigurableType.category == "engagement")
    )
    max_order = max_result.scalar() or 0

    new_type = ConfigurableType(
        category="engagement",
        name=data.name,
        description=data.description,
        color=data.color or "#6366f1",
        sort_order=max_order + 1
    )
    db.add(new_type)
    try:
        await db.commit()
        await db.refresh(new_type)
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Engagement type name must be unique")
    return new_type

@engagement_type_router.put("/{type_id}", response_model=ConfigurableTypeResponse,
                             dependencies=[Depends(require_roles(WRITE_ADMIN_ROLES))])
async def update_engagement_type(
    type_id: str,
    data: ConfigurableTypeUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update an engagement type."""
    result = await db.execute(
        select(ConfigurableType).where(ConfigurableType.id == type_id, ConfigurableType.category == "engagement")
    )
    et = result.scalar_one_or_none()
    if not et:
        raise HTTPException(status_code=404, detail="Engagement type not found")

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(et, key, value)

    try:
        await db.commit()
        await db.refresh(et)
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Engagement type name must be unique")
    return et

@engagement_type_router.delete("/{type_id}", status_code=status.HTTP_204_NO_CONTENT,
                                dependencies=[Depends(require_roles(WRITE_ADMIN_ROLES))])
async def delete_engagement_type(
    type_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Delete an engagement type (blocked if system type or in use)."""
    result = await db.execute(
        select(ConfigurableType).where(ConfigurableType.id == type_id, ConfigurableType.category == "engagement")
    )
    et = result.scalar_one_or_none()
    if not et:
        raise HTTPException(status_code=404, detail="Engagement type not found")

    if et.is_system:
        raise HTTPException(status_code=400, detail="Cannot delete a system engagement type")

    # Check if any engagements reference this type
    usage = await db.execute(select(Engagement).where(Engagement.engagement_type == et.name).limit(1))
    if usage.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Cannot delete type — engagements are using it")

    await db.delete(et)
    await db.commit()
    return None

