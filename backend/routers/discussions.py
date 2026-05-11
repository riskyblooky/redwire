from fastapi import APIRouter, Depends, HTTPException, status
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
from auth.rbac import check_engagement_permission
from models.permission import Permission
from datetime import datetime
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
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    
    if not is_admin:
        has_permission = await check_engagement_permission(current_user.id, thread_data.engagement_id, Permission.DISCUSSION_CREATE.value, db)
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions. You need the 'discussion_create' permission to create threads."
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
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    is_creator = thread.created_by == current_user.id
    
    if not (is_admin or is_creator):
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
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    is_creator = thread.created_by == current_user.id
    
    if not (is_admin or is_creator):
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
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
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
        comment_dict["author_name"] = comment.author.username if comment.author else None
        comment_dict["author_profile_photo"] = comment.author.profile_photo if comment.author else None
        comment_dict["resolver_name"] = comment.resolver.username if comment.resolver else None
        response_comments.append(CommentResponse(**comment_dict))
    
    return response_comments

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
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    
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
    comment_dict["author_name"] = comment.author.username if comment.author else None
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
            link=f"/engagements/{thread.engagement_id}?tab=overview",
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
    comment_dict["author_name"] = comment.author.username if comment.author else None
    comment_dict["author_profile_photo"] = comment.author.profile_photo if comment.author else None
    comment_dict["resolver_name"] = comment.resolver.username if comment.resolver else None
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
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
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
    limit: int = 25,
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
        log_dict["user_name"] = log.user.username if log.user else "System"
        log_dict["user_profile_photo"] = log.user.profile_photo if log.user else None
        response_logs.append(log_dict)
    
    return {"items": response_logs, "total": total}

# Helper function removed - moved to utils.collaboration.create_activity_log
