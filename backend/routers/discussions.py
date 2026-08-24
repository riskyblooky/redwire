from fastapi import APIRouter, Depends, HTTPException, status, Query
from schemas._field_limits import MAX_LIST_LIMIT
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, delete as sql_delete, or_
from sqlalchemy.orm import selectinload
from typing import List, Optional
from database import get_db
from models.user import User, UserRole
from models.discussion import Thread, Comment, ActivityLog, ResourceType
from schemas.discussion import (
    ThreadCreate, ThreadUpdate, ThreadResponse,
    CommentCreate, CommentUpdate, CommentResponse,
    ActivityLogResponse
)
from auth.dependencies import get_current_user
from auth.rbac import check_engagement_permission, is_engagement_member
from models.permission import Permission
from datetime import datetime, timedelta
from utils.collaboration import create_activity_log
from utils.collaboration import manager
import logging

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/discussions", tags=["discussions"])


async def _broadcast_discussion_update(engagement_id: str, thread_id: str, action: str):
    """Push a discussion_update event so clients can drop polling."""
    try:
        await manager.broadcast_to_resource("engagement", engagement_id, {
            "type": "discussion_update",
            "action": action,
            "thread_id": thread_id,
        })
    except Exception as e:
        _logger.warning(f"Failed to broadcast discussion_update: {e}")

# ============ THREADS ============

@router.get("/threads", response_model=List[ThreadResponse])
async def get_threads(
    engagement_id: Optional[str] = None,
    resource_type: Optional[ResourceType] = None,
    resource_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get threads with optional filters."""
    # Authorization Check - need discussion_view permission
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    
    if not is_admin and engagement_id:
        has_permission = await check_engagement_permission(current_user.id, engagement_id, Permission.DISCUSSION_VIEW.value, db)
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions. You need the 'discussion_view' permission to view threads."
            )
    
    query = select(Thread, func.count(Comment.id).label("comment_count")).outerjoin(
        Comment, Thread.id == Comment.thread_id
    ).group_by(Thread.id)
    
    if engagement_id:
        query = query.where(Thread.engagement_id == engagement_id)
    
    if resource_type:
        query = query.where(Thread.resource_type == resource_type.value)
    
    if resource_id:
        query = query.where(Thread.resource_id == resource_id)
    
    # Restrict to assigned engagements for non-admins
    if current_user.role not in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]:
        from models.engagement import Engagement
        from models.user import User
        query = query.join(Engagement).where(
            Engagement.assigned_users.any(User.id == current_user.id)
        )
    
    query = query.order_by(Thread.created_at.desc())
    result = await db.execute(query)
    
    threads_with_counts = []
    for thread, comment_count in result.all():
        thread_dict = ThreadResponse.model_validate(thread).model_dump()
        thread_dict["comment_count"] = comment_count or 0
        threads_with_counts.append(ThreadResponse(**thread_dict))
    
    return threads_with_counts

@router.get("/threads/{thread_id}", response_model=ThreadResponse)
async def get_thread(
    thread_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific thread."""
    result = await db.execute(select(Thread).where(Thread.id == thread_id))
    thread = result.scalar_one_or_none()
    
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")
    
    # Authorization Check - need discussion_view permission
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    
    if not is_admin:
        has_permission = await check_engagement_permission(current_user.id, thread.engagement_id, Permission.DISCUSSION_VIEW.value, db)
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions. You need the 'discussion_view' permission to view this thread."
            )
    
    # Get comment count
    count_result = await db.execute(
        select(func.count(Comment.id)).where(Comment.thread_id == thread_id)
    )
    comment_count = count_result.scalar()
    
    thread_dict = ThreadResponse.model_validate(thread).model_dump()
    thread_dict["comment_count"] = comment_count or 0
    return ThreadResponse(**thread_dict)

@router.post("/threads", response_model=ThreadResponse, status_code=status.HTTP_201_CREATED)
async def create_thread(
    thread_data: ThreadCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new thread."""
    # Authorization Check - need discussion_create permission
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.TEAM_LEAD]
    
    if not is_admin:
        has_permission = await check_engagement_permission(current_user.id, thread_data.engagement_id, Permission.DISCUSSION_CREATE.value, db)
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions. You need the 'discussion_create' permission to create threads."
            )

    # Verify the referenced resource lives in the same engagement as the
    # thread. Without this an attacker could pin a thread (and its
    # downstream WS broadcasts / resource_id metadata) to a foreign
    # engagement's resource id.
    _resource_models = {
        "finding": "models.finding:Finding",
        "testcase": "models.testcase:TestCase",
        "asset": "models.asset:Asset",
        "note": "models.note:Note",
        "vault": "models.vault:VaultItem",
        "cleanup_artifact": "models.cleanup_artifact:CleanupArtifact",
        "evidence": "models.evidence:Evidence",
    }
    rt = thread_data.resource_type.value
    if rt in _resource_models:
        import importlib
        mod_path, cls_name = _resource_models[rt].split(":")
        _model = getattr(importlib.import_module(mod_path), cls_name)
        _res = (await db.execute(
            select(_model).where(_model.id == thread_data.resource_id)
        )).scalar_one_or_none()
        if not _res:
            raise HTTPException(status_code=404, detail=f"{rt.capitalize()} not found")
        if getattr(_res, "engagement_id", None) != thread_data.engagement_id:
            raise HTTPException(
                status_code=400,
                detail=f"{rt.capitalize()} belongs to a different engagement",
            )

    new_thread = Thread(
        engagement_id=thread_data.engagement_id,
        resource_type=thread_data.resource_type.value,  # Use .value to get lowercase string
        resource_id=thread_data.resource_id,
        title=thread_data.title,
        created_by=current_user.id
    )
    db.add(new_thread)
    await db.commit()
    await db.refresh(new_thread)
    
    # Build response immediately before any fire-and-forget work
    response = await get_thread(new_thread.id, db, current_user)

    # Fire-and-forget: activity log (non-fatal)
    try:
        await create_activity_log(
            db=db,
            engagement_id=thread_data.engagement_id,
            user_id=current_user.id,
            action="created_thread",
            resource_type=ResourceType.THREAD,
            resource_id=new_thread.id,
            resource_name=thread_data.title
        )
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass

    await _broadcast_discussion_update(thread_data.engagement_id, new_thread.id, "created_thread")
    return response

@router.put("/threads/{thread_id}", response_model=ThreadResponse)
async def update_thread(
    thread_id: str,
    thread_data: ThreadUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a thread."""
    result = await db.execute(select(Thread).where(Thread.id == thread_id))
    thread = result.scalar_one_or_none()
    
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")
    
    # Check permissions - only creator, admins, or those with discussion_edit permission
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.TEAM_LEAD]
    is_creator = thread.created_by == current_user.id

    if not is_admin:
        # GHSA-7x2f-ff7r-h388 #1 (CWE-863): the previous
        # `if not (is_admin or is_creator)` short-circuit let a user
        # who created a thread keep editing it forever, including
        # after they were removed from the engagement. Gate the
        # creator bypass on current engagement membership.
        if is_creator:
            if not await is_engagement_member(current_user.id, thread.engagement_id, db):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You are no longer a member of this engagement.",
                )
        else:
            has_permission = await check_engagement_permission(current_user.id, thread.engagement_id, Permission.DISCUSSION_EDIT.value, db)
            if not has_permission:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions. You need the 'discussion_edit' permission to modify threads."
                )

    update_data = thread_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(thread, field, value)
    
    await db.commit()
    await db.refresh(thread)
    
    # Build response first
    response = await get_thread(thread_id, db, current_user)

    # Fire-and-forget: activity log
    try:
        await create_activity_log(
            db,
            engagement_id=thread.engagement_id,
            user_id=current_user.id,
            action="updated_thread",
            resource_type=ResourceType.THREAD,
            resource_id=thread.id,
            resource_name=thread.title,
            details=f"Updated thread: {thread.title}"
        )
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass

    await _broadcast_discussion_update(thread.engagement_id, thread.id, "updated_thread")
    return response

@router.put("/threads/{thread_id}/resolve", response_model=ThreadResponse)
async def resolve_thread(
    thread_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Toggle resolve status of a thread."""
    result = await db.execute(select(Thread).where(Thread.id == thread_id))
    thread = result.scalar_one_or_none()
    
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")
    
    # Check permissions
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.TEAM_LEAD]
    is_creator = thread.created_by == current_user.id

    if not is_admin:
        # GHSA-7x2f-ff7r-h388 #1: same ex-member gate as update_thread above.
        if is_creator:
            if not await is_engagement_member(current_user.id, thread.engagement_id, db):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You are no longer a member of this engagement.",
                )
        else:
            has_permission = await check_engagement_permission(current_user.id, thread.engagement_id, Permission.DISCUSSION_EDIT.value, db)
            if not has_permission:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions to resolve this thread."
                )

    thread.is_resolved = not thread.is_resolved
    await db.commit()
    await db.refresh(thread)
    
    # Build response first
    response = await get_thread(thread_id, db, current_user)

    # Fire-and-forget: activity log
    try:
        action_word = "resolved" if thread.is_resolved else "reopened"
        await create_activity_log(
            db,
            engagement_id=thread.engagement_id,
            user_id=current_user.id,
            action=f"{action_word}_thread",
            resource_type=ResourceType.THREAD,
            resource_id=thread.id,
            resource_name=thread.title,
            details=f"{action_word.capitalize()} thread: {thread.title}"
        )
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass
    
    await _broadcast_discussion_update(thread.engagement_id, thread.id, "resolved_thread")
    return response

@router.delete("/threads/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_thread(
    thread_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a thread and all its comments."""
    result = await db.execute(select(Thread).where(Thread.id == thread_id))
    thread = result.scalar_one_or_none()
    
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")
    
    # Check permissions using RBAC with ANY model
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.TEAM_LEAD]
    is_creator = thread.created_by == current_user.id
    
    if not is_admin:
        if is_creator:
            # Creator needs base discussion_delete permission
            has_permission = await check_engagement_permission(current_user.id, thread.engagement_id, Permission.DISCUSSION_DELETE.value, db)
        else:
            # Non-creator needs discussion_delete_any permission
            has_permission = await check_engagement_permission(current_user.id, thread.engagement_id, Permission.DISCUSSION_DELETE_ANY.value, db)
        
        if not has_permission:
            required_perm = Permission.DISCUSSION_DELETE.value if is_creator else Permission.DISCUSSION_DELETE_ANY.value
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. You need the '{required_perm}' permission to delete this thread."
            )
    
    # Log activity before deletion
    await create_activity_log(
        db,
        engagement_id=thread.engagement_id,
        user_id=current_user.id,
        action="deleted_thread",
        resource_type=ResourceType.COMMENT,
        resource_id=thread.id,
        resource_name=thread.title,
        details=f"Deleted thread: {thread.title}"
    )

    engagement_id = thread.engagement_id
    thread_id = thread.id
    await db.delete(thread)
    await db.commit()

    await _broadcast_discussion_update(engagement_id, thread_id, "deleted_thread")
    return None

# ============ COMMENTS ============

@router.get("/comments", response_model=List[CommentResponse])
async def get_comments(
    thread_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all comments for a thread."""
    from sqlalchemy.orm import selectinload
    
    result = await db.execute(
        select(Comment)
        .options(selectinload(Comment.author), selectinload(Comment.resolver))
        .where(Comment.thread_id == thread_id)
        .order_by(Comment.created_at.asc())
    )
    comments = result.scalars().all()
    
    # Enrich with user names
    response_comments = []
    for comment in comments:
        comment_dict = CommentResponse.model_validate(comment).model_dump()
        comment_dict["author_name"] = (comment.author.full_name or comment.author.username) if comment.author else None
        comment_dict["author_profile_photo"] = comment.author.profile_photo if comment.author else None
        comment_dict["resolver_name"] = (comment.resolver.full_name or comment.resolver.username) if comment.resolver else None
        response_comments.append(CommentResponse(**comment_dict))
    
    return response_comments

def _comment_deep_link(thread, comment_id: str) -> str:
    """Build a URL that opens the thread's parent entity and jumps to the
    comment. The frontend reads ?commentId= to expand the thread, scroll to
    the comment, and highlight it."""
    rt = (thread.resource_type or "").lower()
    rid = thread.resource_id
    eid = thread.engagement_id
    if rt == "finding":
        base = f"/findings/{rid}?engagementId={eid}"
    elif rt == "testcase":
        base = f"/testcases/{rid}?engagementId={eid}"
    elif rt == "asset":
        base = f"/assets/{rid}?engagementId={eid}"
    elif rt == "engagement":
        base = f"/engagements/{rid}?tab=overview"
    else:
        base = f"/engagements/{eid}?tab=overview"
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}commentId={comment_id}"


@router.post("/comments", response_model=CommentResponse, status_code=status.HTTP_201_CREATED)
async def create_comment(
    comment_data: CommentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new comment."""
    # Verify thread exists
    thread_result = await db.execute(select(Thread).where(Thread.id == comment_data.thread_id))
    thread = thread_result.scalar_one_or_none()
    
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")
    
    # Authorization Check - need discussion_create permission
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.TEAM_LEAD]
    
    if not is_admin:
        has_permission = await check_engagement_permission(current_user.id, thread.engagement_id, Permission.DISCUSSION_CREATE.value, db)
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions. You need the 'discussion_create' permission to create comments."
            )
    
    new_comment = Comment(
        **comment_data.model_dump(),
        created_by=current_user.id
    )
    db.add(new_comment)
    await db.commit()
    await db.refresh(new_comment)
    
    # Reload with relationships and build response immediately
    result = await db.execute(
        select(Comment)
        .options(selectinload(Comment.author), selectinload(Comment.resolver))
        .where(Comment.id == new_comment.id)
    )
    comment = result.scalar_one()
    
    comment_dict = CommentResponse.model_validate(comment).model_dump()
    comment_dict["author_name"] = (comment.author.full_name or comment.author.username) if comment.author else None
    comment_dict["author_profile_photo"] = comment.author.profile_photo if comment.author else None
    response = CommentResponse(**comment_dict)

    # Fire-and-forget: activity log + notifications (non-fatal)
    try:
        await create_activity_log(
            db=db,
            engagement_id=thread.engagement_id,
            user_id=current_user.id,
            action="commented",
            resource_type=ResourceType.COMMENT,
            resource_id=comment_data.thread_id,
            resource_name=thread.title
        )
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass

    try:
        from utils.collaboration import notify_mentions
        await notify_mentions(
            db=db,
            content=comment.content or "",
            actor_id=current_user.id,
            title=f"You were mentioned in a discussion",
            message=f"{current_user.full_name or current_user.username} mentioned you in thread '{thread.title}'",
            link=_comment_deep_link(thread, new_comment.id),
            engagement_id=thread.engagement_id,
        )
        await db.commit()
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass

    await _broadcast_discussion_update(thread.engagement_id, comment_data.thread_id, "created_comment")
    return response

@router.put("/comments/{comment_id}", response_model=CommentResponse)
async def update_comment(
    comment_id: str,
    comment_data: CommentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Edit a comment's content. Author-only; admins/team-leads may edit any."""
    from sqlalchemy.orm import selectinload

    result = await db.execute(
        select(Comment).options(selectinload(Comment.author), selectinload(Comment.resolver))
        .where(Comment.id == comment_id)
    )
    comment = result.scalar_one_or_none()
    if not comment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")

    # You may only edit your own comment (admins/team-leads may edit any). The
    # author additionally needs discussion_edit on the engagement, mirroring
    # how delete requires discussion_delete.
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        if comment.created_by != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="You can only edit your own comments.")
        thread_r = await db.execute(select(Thread).where(Thread.id == comment.thread_id))
        thread = thread_r.scalar_one_or_none()
        if not thread or not thread.engagement_id or not await check_engagement_permission(
            current_user.id, thread.engagement_id, Permission.DISCUSSION_EDIT.value, db
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions. You need the 'discussion_edit' permission to edit comments.",
            )

    if comment_data.content is not None:
        new_content = comment_data.content.strip()
        if not new_content:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Comment content cannot be empty.")
        comment.content = new_content

    await db.commit()

    result = await db.execute(
        select(Comment).options(selectinload(Comment.author), selectinload(Comment.resolver))
        .where(Comment.id == comment_id)
    )
    comment = result.scalar_one()
    comment_dict = CommentResponse.model_validate(comment).model_dump()
    comment_dict["author_name"] = (comment.author.full_name or comment.author.username) if comment.author else None
    comment_dict["author_profile_photo"] = comment.author.profile_photo if comment.author else None
    comment_dict["resolver_name"] = (comment.resolver.full_name or comment.resolver.username) if comment.resolver else None
    return CommentResponse(**comment_dict)


@router.put("/comments/{comment_id}/resolve", response_model=CommentResponse)
async def resolve_comment(
    comment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Resolve a resolvable comment."""
    from sqlalchemy.orm import selectinload
    
    result = await db.execute(
        select(Comment).options(selectinload(Comment.author))
        .where(Comment.id == comment_id)
    )
    comment = result.scalar_one_or_none()
    
    if not comment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    
    if not comment.is_resolvable:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Comment is not resolvable")
    
    comment.is_resolved = True
    comment.resolved_by = current_user.id
    comment.resolved_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(comment)
    
    # Reload with resolver
    result = await db.execute(
        select(Comment)
        .options(selectinload(Comment.author), selectinload(Comment.resolver))
        .where(Comment.id == comment_id)
    )
    comment = result.scalar_one()
    
    comment_dict = CommentResponse.model_validate(comment).model_dump()
    comment_dict["author_name"] = (comment.author.full_name or comment.author.username) if comment.author else None
    comment_dict["author_profile_photo"] = comment.author.profile_photo if comment.author else None
    comment_dict["resolver_name"] = (comment.resolver.full_name or comment.resolver.username) if comment.resolver else None
    response = CommentResponse(**comment_dict)

    # Get thread for engagement_id
    thread_result2 = await db.execute(select(Thread).where(Thread.id == comment.thread_id))
    thread2 = thread_result2.scalar_one_or_none()
    if thread2:
        await _broadcast_discussion_update(thread2.engagement_id, comment.thread_id, "resolved_comment")

    return response

@router.delete("/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comment(
    comment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a comment."""
    result = await db.execute(select(Comment).where(Comment.id == comment_id))
    comment = result.scalar_one_or_none()
    
    if not comment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    
    # Get thread to check engagement permissions
    thread_result = await db.execute(select(Thread).where(Thread.id == comment.thread_id))
    thread = thread_result.scalar_one_or_none()
    
    # Check permissions using RBAC with ANY model
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.TEAM_LEAD]
    is_creator = comment.created_by == current_user.id
    
    if not is_admin:
        if not thread or not thread.engagement_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
        
        if is_creator:
            # Creator needs base discussion_delete permission
            has_permission = await check_engagement_permission(current_user.id, thread.engagement_id, Permission.DISCUSSION_DELETE.value, db)
        else:
            # Non-creator needs discussion_delete_any permission
            has_permission = await check_engagement_permission(current_user.id, thread.engagement_id, Permission.DISCUSSION_DELETE_ANY.value, db)
        
        if not has_permission:
            required_perm = Permission.DISCUSSION_DELETE.value if is_creator else Permission.DISCUSSION_DELETE_ANY.value
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. You need the '{required_perm}' permission to delete this comment."
            )
    
    thread_id_ref = comment.thread_id
    await db.delete(comment)
    await db.commit()

    if thread:
        await _broadcast_discussion_update(thread.engagement_id, thread_id_ref, "deleted_comment")
    return None

# ============ ACTIVITY LOG ============

@router.get("/activity")
async def get_activity_log(
    engagement_id: str,
    resource_type: Optional[ResourceType] = None,
    user_id: Optional[str] = None,
    action: Optional[str] = None,
    search: Optional[str] = None,
    sort_by: Optional[str] = "created_at",
    sort_order: Optional[str] = "desc",
    limit: int = Query(25, ge=1, le=MAX_LIST_LIMIT),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get activity log for an engagement with filters and pagination."""
    base_query = select(ActivityLog).where(ActivityLog.engagement_id == engagement_id)
    
    if resource_type:
        base_query = base_query.where(ActivityLog.resource_type == resource_type)
        
    if user_id:
        base_query = base_query.where(ActivityLog.user_id == user_id)
        
    if action:
        base_query = base_query.where(ActivityLog.action == action)
        
    if search:
        search_term = f"%{search}%"
        base_query = base_query.where(
            or_(
                ActivityLog.details.ilike(search_term),
                ActivityLog.resource_name.ilike(search_term),
                ActivityLog.action.ilike(search_term)
            )
        )
    
    # Restrict to assigned engagements for non-admins
    if current_user.role not in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]:
        from models.engagement import Engagement
        from models.user import User
        base_query = base_query.join(Engagement).where(
            Engagement.assigned_users.any(User.id == current_user.id)
        )
    
    # Get total count before pagination
    count_query = select(func.count()).select_from(base_query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Sorting
    if sort_by == 'created_at':
        sort_col = ActivityLog.created_at
    elif sort_by == 'action':
        sort_col = ActivityLog.action
    elif sort_by == 'resource_type':
        sort_col = ActivityLog.resource_type
    else:
        sort_col = ActivityLog.created_at

    if sort_order == 'asc':
        base_query = base_query.order_by(sort_col.asc())
    else:
        base_query = base_query.order_by(sort_col.desc())
        
    base_query = base_query.options(selectinload(ActivityLog.user)).offset(offset).limit(limit)
    
    result = await db.execute(base_query)
    logs = result.scalars().all()
    
    # Enrich with user names
    response_logs = []
    for log in logs:
        log_dict = ActivityLogResponse.model_validate(log).model_dump()
        log_dict["user_name"] = (log.user.full_name or log.user.username) if log.user else "System"
        log_dict["user_profile_photo"] = log.user.profile_photo if log.user else None
        response_logs.append(log_dict)
    
    return {"items": response_logs, "total": total}


# ── Activity Feed (content-diff "single pane of glass") ────────────────────
# A content-rich view over the same activity_logs spine: chronological, filtered
# to human-authored content, and enriched with the actual text people posted
# (+ field-level diffs for finding/testcase edits). Built for a team lead who
# needs to see everything happening in an engagement without clicking into each
# resource.

# Resource types that carry content worth surfacing in the feed.
FEED_CONTENT_TYPES = {
    "finding", "testcase", "note", "comment", "asset", "evidence",
    "cleanup_artifact", "vault",
}

# Coarse action buckets → the action-string prefixes they cover.
_FEED_ACTION_PREFIXES = {
    "created": ("created", "uploaded", "imported"),
    "updated": ("updated", "edited", "restored", "stripped", "resolved", "reopened", "linked", "unlinked"),
    "deleted": ("deleted",),
    "commented": ("commented", "created_thread"),
}

_FEED_FIELD_LABELS = {
    "title": "Title", "content": "Content", "category": "Category", "description": "Description",
    "severity": "Severity", "status": "Status", "cvss_score": "CVSS Score",
    "cvss_vector": "CVSS Vector", "impact": "Impact",
    "technical_details": "Technical Details", "steps_to_reproduce": "Steps to Reproduce",
    "mitigations": "Mitigations", "references": "References",
    "steps": "Steps", "expected_result": "Expected Result",
    "actual_result": "Actual Result", "notes": "Notes",
    "is_executed": "Executed", "is_successful": "Successful",
}

_FEED_CONTENT_CAP = 6000


def _feed_action_category(action: str) -> str:
    for cat, prefixes in _FEED_ACTION_PREFIXES.items():
        if any(action.startswith(p) for p in prefixes):
            return cat
    return "other"


def _feed_cap(text) -> Optional[str]:
    if text is None:
        return None
    s = str(text)
    return s if len(s) <= _FEED_CONTENT_CAP else s[:_FEED_CONTENT_CAP] + "\n… (truncated)"


def _feed_as_dt(v):
    if v is None:
        return None
    if isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def _feed_scalarize(v):
    return getattr(v, "value", v)


def _feed_to_text(v) -> str:
    if v is None:
        return ""
    return str(_feed_scalarize(v))


def _feed_diff_for_update(item: dict, snapshots: list, entity, versioned_fields) -> list:
    """Correlate an 'updated' log to the version snapshot taken just before it
    (same request → near-identical timestamp) and diff that pre-edit state
    against the resulting state (the next snapshot, or the live entity if it was
    the most recent edit). Returns [] when no snapshot plausibly matches (e.g. a
    no-op save that skipped snapshotting)."""
    if not snapshots:
        return []
    target = _feed_as_dt(item.get("created_at"))
    if target is None:
        return []
    # Snapshots are the pre-edit state, created microseconds before this log.
    candidates = [s for s in snapshots if s.created_at <= target + timedelta(seconds=2)]
    if not candidates:
        return []
    before = max(candidates, key=lambda s: s.version)
    # If the closest snapshot is far from the log, this edit had no snapshot.
    if abs((target - before.created_at).total_seconds()) > 20:
        return []

    higher = [s for s in snapshots if s.version > before.version]
    if higher:
        after_state = min(higher, key=lambda s: s.version).snapshot or {}
    elif entity is not None:
        after_state = {f: _feed_scalarize(getattr(entity, f, None)) for f in versioned_fields}
    else:
        after_state = {}

    before_snap = before.snapshot or {}
    fields = before.changed_fields or list(versioned_fields)
    changes = []
    for f in fields:
        oldv = before_snap.get(f)
        newv = after_state.get(f)
        if oldv == newv:
            continue
        changes.append({
            "field": f,
            "label": _FEED_FIELD_LABELS.get(f, f),
            "old": _feed_cap(_feed_to_text(oldv)),
            "new": _feed_cap(_feed_to_text(newv)),
        })
    return changes


async def _enrich_feed_items(db: AsyncSession, items: List[dict]):
    """Attach content / diffs to feed items in place, batching per resource type."""
    from models.finding import Finding
    from models.testcase import TestCase
    from models.note import Note
    from models.asset import Asset
    from models.evidence import Evidence
    from models.cleanup_artifact import CleanupArtifact
    from models.vault import VaultItem
    from models.version_history import VersionHistory
    from utils.versioning import FINDING_VERSIONED_FIELDS, TESTCASE_VERSIONED_FIELDS

    by_type: dict = {}
    for it in items:
        by_type.setdefault((it.get("resource_type") or "").lower(), []).append(it)

    async def load_map(model, ids):
        ids = [i for i in ids if i]
        if not ids:
            return {}
        rows = (await db.execute(select(model).where(model.id.in_(ids)))).scalars().all()
        return {r.id: r for r in rows}

    # Findings & test cases — content on create, field diff on update.
    for rtype, model, versioned, entity_type in (
        ("finding", Finding, FINDING_VERSIONED_FIELDS, "finding"),
        ("testcase", TestCase, TESTCASE_VERSIONED_FIELDS, "testcase"),
    ):
        group = by_type.get(rtype, [])
        if not group:
            continue
        ids = {it.get("resource_id") for it in group}
        emap = await load_map(model, ids)
        clean_ids = [i for i in ids if i]
        vrows = (await db.execute(
            select(VersionHistory)
            .where(VersionHistory.entity_type == entity_type)
            .where(VersionHistory.entity_id.in_(clean_ids))
            .order_by(VersionHistory.entity_id, VersionHistory.version.asc())
        )).scalars().all() if clean_ids else []
        vmap: dict = {}
        for v in vrows:
            vmap.setdefault(v.entity_id, []).append(v)

        for it in group:
            ent = emap.get(it.get("resource_id"))
            cat = it.get("action_category")
            if cat == "updated":
                changes = _feed_diff_for_update(it, vmap.get(it.get("resource_id"), []), ent, versioned)
                if changes:
                    it["content_kind"] = "diff"
                    it["changes"] = changes
                # No computable diff (a no-op re-save, or a change to a
                # non-versioned field) → leave it as a plain log line rather than
                # showing the current description as if it were the edit's content.
            elif cat == "created" and ent is not None:
                it["content_kind"] = "text"
                it["content"] = _feed_cap(getattr(ent, "description", None))

    # Notes — full content on create; field diff (title/content) on update.
    group = by_type.get("note", [])
    if group:
        from utils.versioning import NOTE_VERSIONED_FIELDS
        emap = await load_map(Note, {it.get("resource_id") for it in group})
        clean_ids = [i for i in {it.get("resource_id") for it in group} if i]
        vrows = (await db.execute(
            select(VersionHistory)
            .where(VersionHistory.entity_type == "note")
            .where(VersionHistory.entity_id.in_(clean_ids))
            .order_by(VersionHistory.entity_id, VersionHistory.version.asc())
        )).scalars().all() if clean_ids else []
        vmap: dict = {}
        for v in vrows:
            vmap.setdefault(v.entity_id, []).append(v)

        for it in group:
            ent = emap.get(it.get("resource_id"))
            cat = it.get("action_category")
            if cat == "updated":
                changes = _feed_diff_for_update(it, vmap.get(it.get("resource_id"), []), ent, NOTE_VERSIONED_FIELDS)
                if changes:
                    it["content_kind"] = "diff"
                    it["changes"] = changes
                # else: no computable diff (pre-history edit, or non-versioned
                # change) → leave as a plain log line, not the whole note.
            elif cat == "created" and ent is not None:
                it["content_kind"] = "text"
                it["content"] = _feed_cap(ent.content)

    # Assets — identifier + description/notes.
    group = by_type.get("asset", [])
    if group:
        emap = await load_map(Asset, {it.get("resource_id") for it in group})
        for it in group:
            ent = emap.get(it.get("resource_id"))
            if ent is not None and it.get("action_category") in ("created", "updated"):
                body = ent.description or ent.notes
                if body:
                    prefix = f"**{ent.identifier}**\n\n" if getattr(ent, "identifier", None) else ""
                    it["content_kind"] = "text"
                    it["content"] = _feed_cap(prefix + body)

    # Evidence — the caption/description.
    group = by_type.get("evidence", [])
    if group:
        emap = await load_map(Evidence, {it.get("resource_id") for it in group})
        for it in group:
            ent = emap.get(it.get("resource_id"))
            if ent is not None and ent.description:
                it["content_kind"] = "text"
                it["content"] = _feed_cap(ent.description)

    # Cleanup artifacts — location / description / cleanup notes.
    group = by_type.get("cleanup_artifact", [])
    if group:
        emap = await load_map(CleanupArtifact, {it.get("resource_id") for it in group})
        for it in group:
            ent = emap.get(it.get("resource_id"))
            if ent is not None and it.get("action_category") in ("created", "updated"):
                parts = []
                if getattr(ent, "location", None):
                    parts.append(f"**Location:** {ent.location}")
                if ent.description:
                    parts.append(ent.description)
                if getattr(ent, "cleanup_notes", None):
                    parts.append(f"**Cleanup notes:** {ent.cleanup_notes}")
                if parts:
                    it["content_kind"] = "text"
                    it["content"] = _feed_cap("\n\n".join(parts))

    # Vault — only the NON-secret description column. Selected explicitly so the
    # encrypted username/password/note are never loaded or decrypted.
    group = by_type.get("vault", [])
    if group:
        ids = [it.get("resource_id") for it in group if it.get("resource_id")]
        desc_map = {}
        if ids:
            rows = (await db.execute(
                select(VaultItem.id, VaultItem.description).where(VaultItem.id.in_(ids))
            )).all()
            desc_map = {r[0]: r[1] for r in rows}
        for it in group:
            desc = desc_map.get(it.get("resource_id"))
            if desc and it.get("action_category") in ("created", "updated"):
                it["content_kind"] = "text"
                it["content"] = _feed_cap(desc)

    # Comments — resource_id is the THREAD id; pick the comment closest in time.
    group = by_type.get("comment", [])
    if group:
        thread_ids = [it.get("resource_id") for it in group if it.get("resource_id")]
        if thread_ids:
            crows = (await db.execute(
                select(Comment).where(Comment.thread_id.in_(thread_ids))
            )).scalars().all()
            cmap: dict = {}
            for c in crows:
                cmap.setdefault(c.thread_id, []).append(c)
            for it in group:
                comments = cmap.get(it.get("resource_id"), [])
                if not comments:
                    continue
                target = _feed_as_dt(it.get("created_at"))
                best = (min(comments, key=lambda c: abs((c.created_at - target).total_seconds()))
                        if target else comments[-1])
                it["content_kind"] = "text"
                it["content"] = _feed_cap(best.content)

    # vault / cleanup_artifact / engagement: event line only (vault = secret safety).


@router.get("/activity/feed")
async def get_activity_feed(
    engagement_id: str,
    resource_types: Optional[str] = None,      # CSV of resource types
    action_category: Optional[str] = None,     # created | updated | deleted | commented
    user_id: Optional[str] = None,
    search: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    include_all: bool = False,
    sort_order: Optional[str] = "desc",
    limit: int = Query(25, ge=1, le=MAX_LIST_LIMIT),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Content-rich activity feed for an engagement — the activity stream filtered
    to content-bearing events and enriched with the actual text people posted,
    plus field diffs for finding/testcase edits. Same membership scoping as
    ``/activity`` (non-admins see only engagements they're assigned to)."""
    base_query = select(ActivityLog).where(ActivityLog.engagement_id == engagement_id)

    if resource_types:
        types = [t.strip() for t in resource_types.split(",") if t.strip()]
        if types:
            base_query = base_query.where(ActivityLog.resource_type.in_(types))
    elif not include_all:
        base_query = base_query.where(ActivityLog.resource_type.in_(FEED_CONTENT_TYPES))

    if action_category:
        prefixes = _FEED_ACTION_PREFIXES.get(action_category)
        if prefixes:
            base_query = base_query.where(or_(*[ActivityLog.action.like(f"{p}%") for p in prefixes]))

    if user_id:
        base_query = base_query.where(ActivityLog.user_id == user_id)

    if search:
        term = f"%{search}%"
        base_query = base_query.where(or_(
            ActivityLog.details.ilike(term),
            ActivityLog.resource_name.ilike(term),
            ActivityLog.action.ilike(term),
        ))

    if date_from:
        base_query = base_query.where(ActivityLog.created_at >= date_from)
    if date_to:
        base_query = base_query.where(ActivityLog.created_at <= date_to)

    if current_user.role not in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]:
        from models.engagement import Engagement
        base_query = base_query.join(Engagement).where(
            Engagement.assigned_users.any(User.id == current_user.id)
        )

    total = (await db.execute(select(func.count()).select_from(base_query.subquery()))).scalar() or 0

    order = ActivityLog.created_at.asc() if sort_order == "asc" else ActivityLog.created_at.desc()
    page_query = base_query.options(selectinload(ActivityLog.user)).order_by(order).offset(offset).limit(limit)
    logs = (await db.execute(page_query)).scalars().all()

    items = []
    for log in logs:
        d = ActivityLogResponse.model_validate(log).model_dump()
        d["user_name"] = (log.user.full_name or log.user.username) if log.user else "System"
        d["user_profile_photo"] = log.user.profile_photo if log.user else None
        d["action_category"] = _feed_action_category(log.action or "")
        d["content_kind"] = "none"
        d["content"] = None
        d["changes"] = []
        items.append(d)

    await _enrich_feed_items(db, items)
    return {"items": items, "total": total}


# Helper function removed - moved to utils.collaboration.create_activity_log
