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


async def has_engagement_permission(
    user: User,
    engagement_id: str,
    permission: Permission,
    db: AsyncSession
) -> bool:
    """
    Check if user has permission for a specific engagement via their role assignment.
    
    Args:
        user: The user to check permissions for
        engagement_id: The engagement ID to check permissions for
        permission: The permission to verify
        db: Database session
        
    Returns:
        bool: True if user has the permission, False otherwise
    """
    from models.user import UserRole
    # ADMIN and TEAM_LEAD bypass all engagement permissions. READ_ONLY_ADMIN
    # bypasses only read-style permissions; write actions still require an
    # explicit grant via engagement-role permissions below.
    if user.role in (UserRole.ADMIN, UserRole.TEAM_LEAD):
        return True
    if user.role == UserRole.READ_ONLY_ADMIN and _is_read_permission(permission):
        return True
    
    # Verify this is actually an engagement permission
    if permission not in ENGAGEMENT_PERMISSIONS:
        return False
    
    # First check if user has global override permissions
    admin_overrides = {
        Permission.VIEW_ALL_ENGAGEMENTS: [
            Permission.ENGAGEMENT_VIEW,
            Permission.FINDING_VIEW,
            Permission.ASSET_VIEW,
            Permission.TESTCASE_VIEW,
            Permission.EVIDENCE_VIEW,
            Permission.VAULT_VIEW,
            Permission.DISCUSSION_VIEW,
            Permission.REPORT_VIEW,
        ],
    }
    
    for global_perm, granted_eng_perms in admin_overrides.items():
        if permission in granted_eng_perms:
            if await has_global_permission(user, global_perm, db):
                return True
    
    # Query user's role in this specific engagement
    query = (
        select(EngagementRolePermissions.permissions)
        .join(EngagementAssignment, EngagementRolePermissions.role_id == EngagementAssignment.role_id)
        .where(
            EngagementAssignment.user_id == user.id,
            EngagementAssignment.engagement_id == engagement_id
        )
    )
    
    result = await db.execute(query)
    role_permissions = result.scalar_one_or_none()
    
    if role_permissions and permission.value in role_permissions:
        return True
    
    return False


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


async def require_engagement_permission(
    engagement_id: str,
    permission: Permission,
    user: User,
    db: AsyncSession
) -> None:
    """
    Dependency that enforces an engagement-specific permission requirement.
    Raises 403 if user lacks permission.
    
    Args:
        engagement_id: Engagement to check permissions for
        permission: Required permission
        user: Current user
        db: Database session
        
    Raises:
        HTTPException: 403 if permission denied
    """
    if not await has_engagement_permission(user, engagement_id, permission, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions for this engagement. Required: {permission.value}"
        )


async def can_modify_resource(
    resource_owner_id: str,
    current_user: User,
    engagement_id: Optional[str],
    edit_permission: Permission,
    edit_any_permission: Optional[Permission],
    db: AsyncSession
) -> bool:
    """
    Helper to check if user can modify a resource.
    Checks ownership first, then edit_any permission.
    
    Args:
        resource_owner_id: ID of user who created the resource
        current_user: User attempting to modify
        engagement_id: Engagement context (if applicable)
        edit_permission: Basic edit permission
        edit_any_permission: Permission to edit any resource (not just owned)
        db: Database session
        
    Returns:
        bool: True if user can modify
    """
    # Owner can always edit their own
    if resource_owner_id == current_user.id:
        if engagement_id:
            return await has_engagement_permission(current_user, engagement_id, edit_permission, db)
        else:
            return True
    
    # Check if user has "edit any" permission
    if edit_any_permission and engagement_id:
        return await has_engagement_permission(current_user, engagement_id, edit_any_permission, db)
    
    return False


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
    
    # Check for VIEW_ALL_ENGAGEMENTS permission
    for group_perms in all_group_permissions:
        if group_perms and Permission.VIEW_ALL_ENGAGEMENTS.value in group_perms:
            # Grant all view permissions
            permissions_set.update([
                Permission.ENGAGEMENT_VIEW.value,
                Permission.FINDING_VIEW.value,
                Permission.ASSET_VIEW.value,
                Permission.TESTCASE_VIEW.value,
                Permission.EVIDENCE_VIEW.value,
                Permission.VAULT_VIEW.value,
            ])
    
    return list(permissions_set)
