"""
Permission checking utilities for RBAC system.

This module provides centralized permission verification for both global (site-wide)
and engagement-specific permissions.
"""

from functools import wraps
from fastapi import HTTPException, status, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from models.user import User
from models.permission import Permission, GroupPermissions, EngagementRolePermissions, GLOBAL_PERMISSIONS, ENGAGEMENT_PERMISSIONS
from models.group import Group, user_groups
from models.associations import EngagementAssignment
from database import get_db


def _is_read_permission(permission: Permission) -> bool:
    """View-style permissions (e.g. view_all_users, finding_view) are
    read-only; everything else (manage_*, *_create/edit/delete/_any) is
    a write action."""
    v = permission.value
    return v.startswith("view_") or v.endswith("_view")


async def has_global_permission(
    user: User,
    permission: Permission,
    db: AsyncSession
) -> bool:
    """
    Check if user has a global permission via their group memberships.

    Args:
        user: The user to check permissions for
        permission: The permission to verify
        db: Database session

    Returns:
        bool: True if user has the permission, False otherwise
    """
    from models.user import UserRole
    # ADMIN bypasses all checks. READ_ONLY_ADMIN bypasses only read-style
    # permissions — write actions still go through the group membership
    # check below (and will fall through to False unless an explicit
    # group grants it).
    if user.role == UserRole.ADMIN:
        return True
    if user.role == UserRole.READ_ONLY_ADMIN and _is_read_permission(permission):
        return True
    
    # Verify this is actually a global permission
    if permission not in GLOBAL_PERMISSIONS:
        return False
    
    # Query all groups the user belongs to
    query = (
        select(GroupPermissions.permissions)
        .join(Group, GroupPermissions.group_id == Group.id)
        .join(user_groups, Group.id == user_groups.c.group_id)
        .where(user_groups.c.user_id == user.id)
    )
    
    result = await db.execute(query)
    all_group_permissions = result.scalars().all()
    
    # Check if any group grants this permission
    for group_perms in all_group_permissions:
        if group_perms and permission.value in group_perms:
            return True
    
    return False




async def global_permission_set(user: User, db: AsyncSession) -> set:
    """Every global permission value the user effectively holds — the set
    form of has_global_permission, for subset ("ceiling") checks."""
    from models.user import UserRole
    if user.role == UserRole.ADMIN:
        return {p.value for p in GLOBAL_PERMISSIONS}
    held = set()
    if user.role == UserRole.READ_ONLY_ADMIN:
        held = {p.value for p in GLOBAL_PERMISSIONS if _is_read_permission(p)}
    result = await db.execute(
        select(GroupPermissions.permissions)
        .join(user_groups, GroupPermissions.group_id == user_groups.c.group_id)
        .where(user_groups.c.user_id == user.id)
    )
    for perms in result.scalars().all():
        held.update(perms or [])
    return held & {p.value for p in GLOBAL_PERMISSIONS}


async def engagement_permission_ceiling(user: User, db: AsyncSession) -> set:
    """The engagement permissions a user may put on (or take off) an
    engagement role: everything for ADMIN and TEAM_LEAD (both bypass
    engagement permissions everywhere), otherwise the union of what they
    hold in any engagement they're assigned to, plus the view permissions
    their role / VIEW_ALL_ENGAGEMENTS grant. Roles are global templates, so
    "held somewhere" is the only meaningful comparison."""
    from models.user import UserRole
    every = {p.value for p in ENGAGEMENT_PERMISSIONS}
    if user.role in (UserRole.ADMIN, UserRole.TEAM_LEAD):
        return every
    held = set()
    if user.role == UserRole.READ_ONLY_ADMIN:
        held = {p.value for p in ENGAGEMENT_PERMISSIONS if _is_read_permission(p)}
    if Permission.VIEW_ALL_ENGAGEMENTS.value in await global_permission_set(user, db):
        # The one definition of what view-all holds (no vault_view: stored
        # credentials still need an engagement role). A local copy here
        # had vault_view, so a role manager with only view-all could put
        # it on a role.
        from models.permission import VIEW_ALL_ENGAGEMENT_GRANTS
        held.update(VIEW_ALL_ENGAGEMENT_GRANTS)
    result = await db.execute(
        select(EngagementRolePermissions.permissions)
        .join(EngagementAssignment, EngagementRolePermissions.role_id == EngagementAssignment.role_id)
        .where(EngagementAssignment.user_id == user.id)
    )
    for perms in result.scalars().all():
        held.update(perms or [])
    return held & every


async def group_permission_set(group_ids, db: AsyncSession) -> set:
    """Union of the global permissions granted by the given groups."""
    if not group_ids:
        return set()
    result = await db.execute(
        select(GroupPermissions.permissions).where(GroupPermissions.group_id.in_(list(group_ids)))
    )
    held = set()
    for perms in result.scalars().all():
        held.update(perms or [])
    return held


async def require_global_permission(
    permission: Permission,
    user: User,
    db: AsyncSession
) -> None:
    """
    Dependency that enforces a global permission requirement.
    Raises 403 if user lacks permission.
    
    Args:
        permission: Required permission
        user: Current user
        db: Database session
        
    Raises:
        HTTPException: 403 if permission denied
    """
    if not await has_global_permission(user, permission, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions. Required: {permission.value}"
        )






async def get_user_engagement_permissions(
    user_id: str,
    engagement_id: str,
    db: AsyncSession
) -> List[str]:
    """
    Get all permissions a user has for a specific engagement.
    
    Args:
        user_id: The user ID to get permissions for
        engagement_id: The engagement ID to check permissions for
        db: Database session
        
    Returns:
        List of permission strings the user has
    """
    permissions_set = set()
    
    # Get permissions from engagement role assignment
    query = (
        select(EngagementRolePermissions.permissions)
        .join(EngagementAssignment, EngagementRolePermissions.role_id == EngagementAssignment.role_id)
        .where(
            EngagementAssignment.user_id == user_id,
            EngagementAssignment.engagement_id == engagement_id
        )
    )
    
    result = await db.execute(query)
    role_permissions = result.scalar_one_or_none()
    
    if role_permissions:
        permissions_set.update(role_permissions)
    
    # Check for global permissions that grant engagement access
    # For example, VIEW_ALL_ENGAGEMENTS grants all view permissions
    global_query = (
        select(GroupPermissions.permissions)
        .join(Group, GroupPermissions.group_id == Group.id)
        .join(user_groups, Group.id == user_groups.c.group_id)
        .where(user_groups.c.user_id == user_id)
    )
    
    global_result = await db.execute(global_query)
    all_group_permissions = global_result.scalars().all()
    
    # VIEW_ALL_ENGAGEMENTS: the same grant check_engagement_permission
    # applies (it used to list VAULT_VIEW here, so the UI offered a vault tab
    # the API then refused).
    from models.permission import VIEW_ALL_ENGAGEMENT_GRANTS
    for group_perms in all_group_permissions:
        if group_perms and Permission.VIEW_ALL_ENGAGEMENTS.value in group_perms:
            permissions_set.update(VIEW_ALL_ENGAGEMENT_GRANTS)
    
    return list(permissions_set)
