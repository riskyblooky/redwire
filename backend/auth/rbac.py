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

_ADMIN_ROLES = (UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD)


async def resolve_engagement_scope(
    engagement_id: Optional[str],
    db: AsyncSession,
    current_user,
):
    """Resolve the engagement-scoping context for an aggregate-read endpoint.

    Returns ``(is_admin, allowed_eng_subq)``:
      - ``is_admin`` — True for ADMIN / READ_ONLY_ADMIN / TEAM_LEAD; those
        callers bypass engagement scoping entirely.
      - ``allowed_eng_subq`` — a SQLAlchemy scalar subquery yielding the
        engagement ids the caller is assigned to. Use with
        ``column.in_(allowed_eng_subq)`` via ``scope_to_assignments``.

    If ``engagement_id`` is supplied by a non-admin caller, the caller's
    membership on that engagement is verified; if absent, raises 403.
    """
    is_admin = current_user.role in _ADMIN_ROLES
    allowed_eng_subq = (
        select(EngagementAssignment.engagement_id)
        .where(EngagementAssignment.user_id == current_user.id)
        .scalar_subquery()
    )
    if engagement_id and not is_admin:
        member = await db.execute(
            select(EngagementAssignment.user_id).where(
                EngagementAssignment.user_id == current_user.id,
                EngagementAssignment.engagement_id == engagement_id,
            )
        )
        if not member.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions for this engagement.",
            )
    return is_admin, allowed_eng_subq


def scope_to_assignments(query, column, engagement_id, is_admin, allowed_eng_subq):
    """Apply engagement scoping to an aggregate-read query.

    Use after ``resolve_engagement_scope``:
      - if ``engagement_id`` is supplied, filter the query to that engagement;
      - else if the caller is non-admin, restrict to their assigned engagements;
      - else (admin, no scope) return the query unchanged.
    """
    if engagement_id:
        return query.where(column == engagement_id)
    if not is_admin:
        return query.where(column.in_(allowed_eng_subq))
    return query


# ── stats-page scope toggle ──────────────────────────────────────────
#
# The post-GHSA-ffmc stats endpoints scope counts to the caller's assigned
# engagements. An admin can flip the platform-wide STATS_SCOPE_MODE setting
# to "global" so non-admin operators see platform-wide aggregates instead.
# To make global-mode safe by default, non-admin responses in global mode
# are *anonymised*: engagement/client/user names are stripped, only counts
# and aggregates remain. Scoped mode keeps full identifiers since the data
# is already restricted to the caller's own engagements.

_STATS_SCOPE_MODE_KEY = "STATS_SCOPE_MODE"
_STATS_SCOPE_MODE_DEFAULT = "global"
_STATS_SCOPE_MODE_VALID = {"global", "scoped"}


async def get_stats_scope_mode(db: AsyncSession) -> str:
    """Return the current stats-scope mode ("global" or "scoped").

    Defaults to "global" if the key isn't set yet. Unknown values fall
    back to the default rather than letting a typo lock the page.
    """
    from models.auth_settings import AuthSetting  # avoid import cycle

    result = await db.execute(
        select(AuthSetting.value).where(AuthSetting.key == _STATS_SCOPE_MODE_KEY)
    )
    raw = result.scalar_one_or_none()
    if raw and raw.strip().lower() in _STATS_SCOPE_MODE_VALID:
        return raw.strip().lower()
    return _STATS_SCOPE_MODE_DEFAULT


async def apply_stats_scope(
    engagement_id: Optional[str],
    db: AsyncSession,
    current_user,
):
    """Resolve the scoping context for a stats/analytics endpoint.

    Returns ``(is_admin_effective, allowed_eng_subq, strip_identifiers)``:
      - ``is_admin_effective`` — feed straight into ``scope_to_assignments``.
        True for actual admins, also True for non-admins when the toggle is
        in "global" mode (their query returns platform-wide counts).
      - ``allowed_eng_subq`` — same shape as ``resolve_engagement_scope``.
      - ``strip_identifiers`` — True when the caller is a non-admin in
        global mode; the handler MUST null out engagement/client/user names
        before returning so platform-wide counts don't leak identities.

    Admins always see full data. ``engagement_id`` narrowing still 403s
    a non-admin who isn't on that engagement, regardless of mode — the
    mode only affects the no-engagement-supplied path.
    """
    is_admin = current_user.role in _ADMIN_ROLES

    if engagement_id and not is_admin:
        member = await db.execute(
            select(EngagementAssignment.user_id).where(
                EngagementAssignment.user_id == current_user.id,
                EngagementAssignment.engagement_id == engagement_id,
            )
        )
        if not member.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions for this engagement.",
            )

    allowed_eng_subq = (
        select(EngagementAssignment.engagement_id)
        .where(EngagementAssignment.user_id == current_user.id)
        .scalar_subquery()
    )

    if is_admin:
        return True, allowed_eng_subq, False

    # Non-admin path. If they pinned an engagement_id they own, scope
    # tightly to it (the mode is irrelevant). Otherwise consult the mode.
    if engagement_id:
        return False, allowed_eng_subq, False

    mode = await get_stats_scope_mode(db)
    if mode == "global":
        # Bypass the scope filter (is_admin_effective=True) but flag
        # the handler to strip names before returning.
        return True, allowed_eng_subq, True
    # scoped mode — behave exactly like resolve_engagement_scope.
    return False, allowed_eng_subq, False


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

