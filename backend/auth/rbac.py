from functools import wraps
from fastapi import HTTPException, status
from models.user import UserRole
from models.associations import EngagementAssignment
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

def require_roles(allowed_roles: List[UserRole]):
    """Decorator to enforce RBAC on endpoints."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Get current_user from kwargs
            current_user = kwargs.get("current_user")
            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required"
                )
            
            # Check if user's role is in allowed roles
            if current_user.role not in allowed_roles:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Insufficient permissions. Required roles: {[r.value for r in allowed_roles]}"
                )
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator

async def check_engagement_role(user_id: str, engagement_id: str, allowed_role_names: List[str], db: AsyncSession) -> bool:
    """Check if a user has one of the allowed roles on a specific engagement."""
    from models.engagement_role import EngagementRole
    
    query = (
        select(EngagementRole.name)
        .join(EngagementAssignment)
        .where(
            EngagementAssignment.user_id == user_id,
            EngagementAssignment.engagement_id == engagement_id
        )
    )
    result = await db.execute(query)
    role_name = result.scalar_one_or_none()
    
    return role_name in allowed_role_names

async def check_engagement_permission(user_id: str, engagement_id: str, required_permission: str, db: AsyncSession) -> bool:
    """Check if a user has a specific permission on an engagement based on their role's permissions.
    
    Args:
        user_id: The user's ID
        engagement_id: The engagement ID
        required_permission: The permission string (e.g., 'asset_edit', 'finding_delete')
        db: Database session
        
    Returns:
        True if user has the permission, False otherwise
    """
    from models.engagement_role import EngagementRole
    from models.permission import EngagementRolePermissions
    
    # Query to get the user's role permissions for this engagement
    query = (
        select(EngagementRolePermissions.permissions)
        .join(EngagementRole, EngagementRolePermissions.role_id == EngagementRole.id)
        .join(EngagementAssignment, EngagementAssignment.role_id == EngagementRole.id)
        .where(
            EngagementAssignment.user_id == user_id,
            EngagementAssignment.engagement_id == engagement_id
        )
    )
    result = await db.execute(query)
    permissions = result.scalar_one_or_none()
    
    if not permissions:
        return False
    
    # Check if the required permission is in the user's role permissions
    return required_permission in permissions

def can_modify_resource(resource_owner_id: str, current_user, engagement_role: Optional[str] = None) -> bool:
    """Check if user can modify a resource."""
    # Admins and Team Leads can modify anything
    if current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]:
        return True
    
    # Check engagement-level role if provided
    if engagement_role:
        if engagement_role == "Engagement Lead":
            return True
        # Operators might be allowed based on higher-level logic (e.g. adding vs editing)
    
    # Operators can only modify their own resources
    if current_user.role == UserRole.OPERATOR:
        return resource_owner_id == current_user.id
    
    # Read-only cannot modify anything
    return False

