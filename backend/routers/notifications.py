from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, delete
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime

from database import get_db
from models.user import User
from models.notification import Notification, NotificationPreference, EVENT_TYPES
from auth.dependencies import get_current_user

router = APIRouter(prefix="/notifications", tags=["notifications"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class NotificationResponse(BaseModel):
    id: str
    user_id: str
    event_type: str
    title: str
    message: Optional[str] = None
    link: Optional[str] = None
    is_read: bool
    actor_id: Optional[str] = None
    actor_name: Optional[str] = None
    engagement_id: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class NotificationPreferenceResponse(BaseModel):
    event_type: str
    label: str
    site_muted: bool
    email_muted: bool


class NotificationPreferenceUpdate(BaseModel):
    event_type: str = Field(..., max_length=64)
    site_muted: bool
    email_muted: bool


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("", response_model=List[NotificationResponse])
async def get_notifications(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    unread_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List current user's notifications, newest first."""
    query = (
        select(
            Notification,
            User.full_name.label("actor_name"),
        )
        .outerjoin(User, Notification.actor_id == User.id)
        .where(Notification.user_id == current_user.id)
    )
    if unread_only:
        query = query.where(Notification.is_read == False)
    query = query.order_by(Notification.created_at.desc()).offset(skip).limit(limit)

    result = await db.execute(query)
    rows = result.all()

    return [
        NotificationResponse(
            id=n.id,
            user_id=n.user_id,
            event_type=n.event_type,
            title=n.title,
            message=n.message,
            link=n.link,
            is_read=n.is_read,
            actor_id=n.actor_id,
            actor_name=actor_name,
            engagement_id=n.engagement_id,
            created_at=n.created_at,
        )
        for n, actor_name in rows
    ]


@router.get("/unread-count")
async def get_unread_count(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get count of unread notifications."""
    result = await db.execute(
        select(func.count(Notification.id)).where(
            Notification.user_id == current_user.id,
            Notification.is_read == False,
        )
    )
    count = result.scalar() or 0
    return {"count": count}


@router.patch("/{notification_id}/read")
async def mark_read(
    notification_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark a notification as read."""
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
    )
    notification = result.scalar_one_or_none()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    notification.is_read = True
    await db.commit()
    return {"ok": True}


@router.post("/mark-all-read")
async def mark_all_read(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark all notifications as read."""
    await db.execute(
        update(Notification)
        .where(Notification.user_id == current_user.id, Notification.is_read == False)
        .values(is_read=True)
    )
    await db.commit()
    return {"ok": True}


@router.post("/clear-all")
async def clear_all_notifications(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete all notifications for the current user."""
    await db.execute(
        delete(Notification).where(Notification.user_id == current_user.id)
    )
    await db.commit()
    return {"ok": True}


@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a notification."""
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
    )
    notification = result.scalar_one_or_none()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    await db.delete(notification)
    await db.commit()
    return {"ok": True}


# ── Preferences ──────────────────────────────────────────────────────────────

@router.get("/preferences", response_model=List[NotificationPreferenceResponse])
async def get_preferences(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get notification preferences for all event types."""
    result = await db.execute(
        select(NotificationPreference).where(
            NotificationPreference.user_id == current_user.id
        )
    )
    prefs = {p.event_type: p for p in result.scalars().all()}

    # Return all event types, filling in defaults for missing ones
    response = []
    for event_type, label in EVENT_TYPES.items():
        pref = prefs.get(event_type)
        response.append(
            NotificationPreferenceResponse(
                event_type=event_type,
                label=label,
                site_muted=pref.site_muted if pref else False,
                email_muted=pref.email_muted if pref else True,
            )
        )
    return response


@router.put("/preferences")
async def update_preferences(
    preferences: List[NotificationPreferenceUpdate],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update notification preferences."""
    for pref_data in preferences:
        if pref_data.event_type not in EVENT_TYPES:
            continue

        result = await db.execute(
            select(NotificationPreference).where(
                NotificationPreference.user_id == current_user.id,
                NotificationPreference.event_type == pref_data.event_type,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.site_muted = pref_data.site_muted
            existing.email_muted = pref_data.email_muted
        else:
            new_pref = NotificationPreference(
                user_id=current_user.id,
                event_type=pref_data.event_type,
                site_muted=pref_data.site_muted,
                email_muted=pref_data.email_muted,
            )
            db.add(new_pref)

    await db.commit()
    return {"ok": True}
