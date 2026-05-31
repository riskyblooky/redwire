"""
Admin endpoints for managing groups, roles, and permissions.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from typing import List
from database import get_db
from auth.dependencies import get_current_user, require_roles, ADMIN_ROLES
from auth.permissions import has_global_permission, require_global_permission
from models.user import User, UserRole
from models.group import Group
from models.engagement_role import EngagementRole
from models.permission import (
    Permission,
    GroupPermissions,
    EngagementRolePermissions,
    PERMISSION_CATEGORIES,
    GLOBAL_PERMISSIONS,
    ENGAGEMENT_PERMISSIONS
)
from pydantic import BaseModel

router = APIRouter(prefix="/admin/permissions", tags=["admin", "permissions"])


# ============ Schemas ============

class PermissionInfo(BaseModel):
    """Information about a permission."""
    name: str
    value: str
    is_global: bool
    is_engagement: bool


class PermissionCategoryResponse(BaseModel):
    """Permission category with list of permissions."""
    category: str
    permissions: List[PermissionInfo]


class GroupBase(BaseModel):
    """Base group schema."""
    name: str
    description: str | None = None


class GroupCreate(GroupBase):
    """Schema for creating a group."""
    pass


class GroupUpdate(GroupBase):
    """Schema for updating a group."""
    pass


class GroupPermissionsUpdate(BaseModel):
    """Schema for updating group permissions."""
    permissions: List[str]


class GroupResponse(BaseModel):
    """Group response with permission details."""
    id: str
    name: str
    description: str | None
    permissions: List[str]
    member_count: int | None = None
    is_system: bool = False
    is_default: bool = False

    class Config:
        from_attributes = True


class EngagementRoleBase(BaseModel):
    """Base engagement role schema."""
    name: str
    description: str | None = None


class EngagementRoleCreate(EngagementRoleBase):
    """Schema for creating an engagement role."""
    pass


class EngagementRoleUpdate(EngagementRoleBase):
    """Schema for updating an engagement role."""
    pass


class EngagementRolePermissionsUpdate(BaseModel):
    """Schema for updating role permissions."""
    permissions: List[str]


class EngagementRoleResponse(BaseModel):
    """Role response with permission details."""
    id: str
    name: str
    description: str | None
    permissions: List[str]

    class Config:
        from_attributes = True


# ============ Permission Listing ============

@router.get(
    "/list",
    response_model=List[PermissionCategoryResponse],
    dependencies=[Depends(require_roles(ADMIN_ROLES))],
)
async def list_permissions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all available permissions organized by category."""
    
    result = []
    for category, perms in PERMISSION_CATEGORIES.items():
        perm_infos = []
        for perm in perms:
            perm_infos.append(PermissionInfo(
                name=perm.value.replace('_', ' ').title(),
                value=perm.value,
                is_global=perm in GLOBAL_PERMISSIONS,
                is_engagement=perm in ENGAGEMENT_PERMISSIONS
            ))
        result.append(PermissionCategoryResponse(
            category=category,
            permissions=perm_infos
        ))
    
    return result


# ============ Group Management ============

@router.get(
    "/groups",
    response_model=List[GroupResponse],
    dependencies=[Depends(require_roles(ADMIN_ROLES))],
)
async def list_groups(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all groups with their permissions."""
    
    from sqlalchemy.orm import selectinload
    
    query = select(Group).options(
        selectinload(Group.permission_set),
        selectinload(Group.users),
    )
    result = await db.execute(query)
    groups = result.scalars().all()
    
    response = []
    for group in groups:
        perms = []
        if group.permission_set:
            perms = group.permission_set.permissions or []
        
        response.append(GroupResponse(
            id=group.id,
            name=group.name,
            description=group.description,
            permissions=perms,
            member_count=len(group.users),
            is_system=group.is_system,
            is_default=group.is_default,
        ))
    
    return response


@router.post("/groups", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
async def create_group(
    group_data: GroupCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new group."""
    await require_global_permission(Permission.MANAGE_GROUPS, current_user, db)
    
    # Check if group name already exists
    existing = await db.execute(select(Group).where(Group.name == group_data.name))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Group with this name already exists"
        )
    
    # Create group
    new_group = Group(
        name=group_data.name,
        description=group_data.description
    )
    db.add(new_group)
    await db.flush()
    
    # Create empty permissions set
    group_perms = GroupPermissions(
        group_id=new_group.id,
        permissions=[]
    )
    db.add(group_perms)
    await db.commit()
    await db.refresh(new_group)
    
    return GroupResponse(
        id=new_group.id,
        name=new_group.name,
        description=new_group.description,
        permissions=[],
        member_count=0
    )


@router.put("/groups/{group_id}", response_model=GroupResponse)
async def update_group(
    group_id: str,
    group_data: GroupUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a group's basic info."""
    await require_global_permission(Permission.MANAGE_GROUPS, current_user, db)
    
    from sqlalchemy.orm import selectinload
    
    query = select(Group).options(selectinload(Group.permission_set)).where(Group.id == group_id)
    result = await db.execute(query)
    group = result.scalar_one_or_none()
    
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    group.name = group_data.name
    group.description = group_data.description
    
    await db.commit()
    await db.refresh(group)
    
    perms = group.permission_set.permissions if group.permission_set else []
    
    return GroupResponse(
        id=group.id,
        name=group.name,
        description=group.description,
        permissions=perms,
        member_count=0  # TODO: Calculate member count with proper eager loading
    )


@router.delete("/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(
    group_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a group."""
    await require_global_permission(Permission.MANAGE_GROUPS, current_user, db)
    
    from sqlalchemy.orm import selectinload
    
    query = select(Group).options(selectinload(Group.permission_set)).where(Group.id == group_id)
    result = await db.execute(query)
    group = result.scalar_one_or_none()
    
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    if group.is_system or group.is_default:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete a system or default group"
        )
    
    await db.delete(group)
    await db.commit()


@router.put("/groups/{group_id}/permissions", response_model=GroupResponse)
async def update_group_permissions(
    group_id: str,
    perm_data: GroupPermissionsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update permissions for a group."""
    await require_global_permission(Permission.MANAGE_GROUPS, current_user, db)

    # GHSA-v2j8-mw59-w33v: least-privilege ceiling. A caller may only grant
    # permissions they themselves hold. has_global_permission already returns
    # True unconditionally for UserRole.ADMIN so admins are unaffected.
    for perm_value in perm_data.permissions:
        try:
            perm = Permission(perm_value)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid permission: {perm_value}"
            )
        if perm not in GLOBAL_PERMISSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Permission '{perm_value}' is not a global permission"
            )
        if not await has_global_permission(current_user, perm, db):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Cannot grant permission '{perm_value}' which you do not hold"
            )

    # Get group
    from sqlalchemy.orm import selectinload

    query = select(Group).options(selectinload(Group.permission_set)).where(Group.id == group_id)
    result = await db.execute(query)
    group = result.scalar_one_or_none()

    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    # GHSA-v2j8-mw59-w33v: mirror the delete-side guard. System / default
    # groups (e.g. Default — every user) must not be mutated via this route
    # by a non-admin manager.
    if group.is_system or group.is_default:
        is_admin = current_user.role == UserRole.ADMIN
        if not is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot modify permissions on a system or default group"
            )
    
    # Update or create permissions
    if group.permission_set:
        group.permission_set.permissions = perm_data.permissions
    else:
        group_perms = GroupPermissions(
            group_id=group.id,
            permissions=perm_data.permissions
        )
        db.add(group_perms)
    
    await db.commit()
    await db.refresh(group)
    
    return GroupResponse(
        id=group.id,
        name=group.name,
        description=group.description,
        permissions=perm_data.permissions,
        member_count=0  # TODO: Calculate member count with proper eager loading
    )


# ============ Engagement Role Management ============

@router.get(
    "/engagement-roles",
    response_model=List[EngagementRoleResponse],
    dependencies=[Depends(require_roles(ADMIN_ROLES))],
)
async def list_engagement_roles(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all engagement roles with their permissions."""
    
    from sqlalchemy.orm import selectinload
    
    query = select(EngagementRole).options(selectinload(EngagementRole.permission_set))
    result = await db.execute(query)
    roles = result.scalars().all()
    
    response = []
    for role in roles:
        perms = []
        if role.permission_set:
            perms = role.permission_set.permissions or []
        
        response.append(EngagementRoleResponse(
            id=role.id,
            name=role.name,
            description=role.description,
            permissions=perms
        ))
    
    return response


@router.post("/engagement-roles", response_model=EngagementRoleResponse, status_code=status.HTTP_201_CREATED)
async def create_engagement_role(
    role_data: EngagementRoleCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new engagement role."""
    await require_global_permission(Permission.MANAGE_ENGAGEMENT_ROLES, current_user, db)
    
    # Check if role name already exists
    existing = await db.execute(select(EngagementRole).where(EngagementRole.name == role_data.name))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Engagement role with this name already exists"
        )
    
    # Create role
    new_role = EngagementRole(
        name=role_data.name,
        description=role_data.description
    )
    db.add(new_role)
    await db.flush()
    
    # Create empty permissions set
    role_perms = EngagementRolePermissions(
        role_id=new_role.id,
        permissions=[]
    )
    db.add(role_perms)
    await db.commit()
    await db.refresh(new_role)
    
    return EngagementRoleResponse(
        id=new_role.id,
        name=new_role.name,
        description=new_role.description,
        permissions=[]
    )


@router.put("/engagement-roles/{role_id}", response_model=EngagementRoleResponse)
async def update_engagement_role(
    role_id: str,
    role_data: EngagementRoleUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update an engagement role's basic info."""
    await require_global_permission(Permission.MANAGE_ENGAGEMENT_ROLES, current_user, db)
    
    from sqlalchemy.orm import selectinload
    
    query = select(EngagementRole).options(selectinload(EngagementRole.permission_set)).where(EngagementRole.id == role_id)
    result = await db.execute(query)
    role = result.scalar_one_or_none()
    
    if not role:
        raise HTTPException(status_code=404, detail="Engagement role not found")
    
    role.name = role_data.name
    role.description = role_data.description
    
    await db.commit()
    await db.refresh(role)
    
    perms = role.permission_set.permissions if role.permission_set else []
    
    return EngagementRoleResponse(
        id=role.id,
        name=role.name,
        description=role.description,
        permissions=perms
    )


@router.delete("/engagement-roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_engagement_role(
    role_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete an engagement role."""
    await require_global_permission(Permission.MANAGE_ENGAGEMENT_ROLES, current_user, db)
    
    from sqlalchemy.orm import selectinload
    
    query = select(EngagementRole).options(selectinload(EngagementRole.permission_set)).where(EngagementRole.id == role_id)
    result = await db.execute(query)
    role = result.scalar_one_or_none()
    
    if not role:
        raise HTTPException(status_code=404, detail="Engagement role not found")
    
    await db.delete(role)
    await db.commit()


@router.put("/engagement-roles/{role_id}/permissions", response_model=EngagementRoleResponse)
async def update_engagement_role_permissions(
    role_id: str,
    perm_data: EngagementRolePermissionsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update permissions for an engagement role."""
    await require_global_permission(Permission.MANAGE_ENGAGEMENT_ROLES, current_user, db)
    
    # Validate all permissions are engagement permissions
    for perm_value in perm_data.permissions:
        try:
            perm = Permission(perm_value)
            if perm not in ENGAGEMENT_PERMISSIONS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Permission '{perm_value}' is not an engagement permission"
                )
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid permission: {perm_value}"
            )
    
    # Get role
    from sqlalchemy.orm import selectinload
    
    query = select(EngagementRole).options(selectinload(EngagementRole.permission_set)).where(EngagementRole.id == role_id)
    result = await db.execute(query)
    role = result.scalar_one_or_none()
    
    if not role:
        raise HTTPException(status_code=404, detail="Engagement role not found")
    
    # Update or create permissions
    if role.permission_set:
        role.permission_set.permissions = perm_data.permissions
    else:
        role_perms = EngagementRolePermissions(
            role_id=role.id,
            permissions=perm_data.permissions
        )
        db.add(role_perms)
    
    await db.commit()
    await db.refresh(role)
    
    return EngagementRoleResponse(
        id=role.id,
        name=role.name,
        description=role.description,
        permissions=perm_data.permissions
    )
