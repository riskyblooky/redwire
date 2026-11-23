"""
Permission checking utilities for RBAC system.

Global (site-wide, group-granted) permissions. Engagement permissions live in
auth/rbac.py (has_engagement_perm / require_engagement_perm and the set form,
engagement_permissions).
"""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from models.user import User
from models.permission import Permission, GroupPermissions, EngagementRolePermissions, GLOBAL_PERMISSIONS, ENGAGEMENT_PERMISSIONS
from models.group import Group, user_groups
from models.associations import EngagementAssignment


# View-style permissions are reads (one rule, shared with the engagement checks).
from auth.rbac import is_read_permission as _is_read_permission  # noqa: E402


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
