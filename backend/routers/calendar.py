from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func, distinct
from sqlalchemy.orm import selectinload

from typing import List, Optional
from database import get_db
from models.user import User, UserRole
from models.calendar import CalendarEvent
from models.engagement import Engagement
from models.engagement_phase import EngagementPhase
from models.associations import EngagementAssignment
from models.skill import UserSkill, Skill, SkillCategory
from schemas.calendar import CalendarEventCreate, CalendarEventUpdate, CalendarEventResponse
from auth.dependencies import get_current_user
from auth.permissions import has_global_permission
from models.permission import Permission
from datetime import datetime

router = APIRouter(prefix="/calendar", tags=["calendar"])

@router.get("/events", response_model=List[CalendarEventResponse])
async def get_calendar_events(
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get manual calendar events within a time range."""
    # Check global calendar_view permission
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        has_perm = await has_global_permission(current_user, Permission.CALENDAR_VIEW, db)
        if not has_perm:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions. You need the 'calendar_view' permission to view calendar events."
            )

    query = select(CalendarEvent)
    
    if start and end:
        start_naive = start.replace(tzinfo=None) if start.tzinfo else start
        end_naive = end.replace(tzinfo=None) if end.tzinfo else end
        query = query.where(
            CalendarEvent.start_time <= end_naive,
            CalendarEvent.end_time >= start_naive
        )

    result = await db.execute(query)
    return result.scalars().all()

@router.post("/events", response_model=CalendarEventResponse, status_code=status.HTTP_201_CREATED)
async def create_calendar_event(
    event_data: CalendarEventCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new manual calendar event."""
    # An Out-of-Office block is self-service availability — it is always
    # created for the caller themselves (created_by below) and is
    # creator-only to edit/delete — so any authenticated user may create
    # one. Regular (shared) events still require the global calendar_create
    # permission.
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.TEAM_LEAD]
    is_ooo = (event_data.event_type or "EVENT").upper() == "OOO"
    if not is_admin and not is_ooo:
        has_perm = await has_global_permission(current_user, Permission.CALENDAR_CREATE, db)
        if not has_perm:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions. You need the 'calendar_create' permission to create calendar events."
            )

    new_event = CalendarEvent(
        **event_data.model_dump(),
        created_by=current_user.id
    )
    
    db.add(new_event)
    await db.commit()
    await db.refresh(new_event)
    return new_event

@router.put("/events/{event_id}", response_model=CalendarEventResponse)
async def update_calendar_event(
    event_id: str,
    event_data: CalendarEventUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a manual calendar event."""
    result = await db.execute(select(CalendarEvent).where(CalendarEvent.id == event_id))
    event = result.scalar_one_or_none()
    
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    
    # Check global calendar_edit permission
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        has_perm = await has_global_permission(current_user, Permission.CALENDAR_EDIT, db)
        if not has_perm:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions. You need the 'calendar_edit' permission to modify calendar events."
            )

    # GHSA-fpj5-2p59-xq8r: OOO events are creator-only (mirrors DELETE), and
    # event_type is frozen at create time so a caller can't flip another
    # user's OOO to a non-OOO type to bypass the OOO guard on the DELETE path.
    if event.event_type == "OOO" and not is_admin and event.created_by != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only edit your own Out of Office events.",
        )
    update_data = event_data.model_dump(exclude_unset=True, exclude={"event_type"})
    for field, value in update_data.items():
        setattr(event, field, value)
        
    event.updated_by = current_user.id
        
    await db.commit()
    await db.refresh(event)
    return event

@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_calendar_event(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a manual calendar event."""
    result = await db.execute(select(CalendarEvent).where(CalendarEvent.id == event_id))
    event = result.scalar_one_or_none()
    
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.TEAM_LEAD]

    # OOO events: only the creator or admin can delete
    if event.event_type == "OOO":
        if not is_admin and event.created_by != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only delete your own Out of Office events."
            )
    else:
        # Regular events: check calendar_delete permission
        if not is_admin:
            has_perm = await has_global_permission(current_user, Permission.CALENDAR_DELETE, db)
            if not has_perm:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions. You need the 'calendar_delete' permission to delete calendar events."
                )
        
    await db.delete(event)
    await db.commit()
    return None

@router.get("/feed")
async def get_calendar_feed(
    start: datetime = Query(...),
    end: datetime = Query(...),
    user_ids: Optional[str] = Query(None, description="Comma-separated user IDs to filter by"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a unified feed of engagement timelines and manual events."""
    # Check global calendar_view permission
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        has_perm = await has_global_permission(current_user, Permission.CALENDAR_VIEW, db)
        if not has_perm:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions. You need the 'calendar_view' permission to view the calendar feed."
            )

    # Ensure naive datetimes for SQL comparison against naive columns
    start_naive = start.replace(tzinfo=None) if start.tzinfo else start
    end_naive = end.replace(tzinfo=None) if end.tzinfo else end

    # Parse user_ids filter
    filter_user_ids = [uid.strip() for uid in user_ids.split(",")] if user_ids else None

    # Overlap logic: EventStart <= RangeEnd AND EventEnd >= RangeStart
    
    # Fetch manual events with creator info for OOO
    event_query = select(CalendarEvent).options(
        selectinload(CalendarEvent.created_by_user)
    ).where(
        CalendarEvent.start_time <= end_naive,
        CalendarEvent.end_time >= start_naive
    )
    events_result = await db.execute(event_query)
    manual_events = events_result.scalars().all()
    
    # Fetch engagements overlapping with the range, plus their phases
    eng_query = select(Engagement).options(
        selectinload(Engagement.assigned_users),
        selectinload(Engagement.phases),
    ).where(
        Engagement.start_date <= end_naive,
        or_(
            Engagement.end_date >= start_naive,
            Engagement.end_date.is_(None)
        )
    )
    # GHSA-fpj5-2p59-xq8r: CALENDAR_VIEW alone must not enumerate every
    # client's engagement. Confine to the caller's own assignments unless
    # they hold VIEW_ALL_ENGAGEMENTS (or are admin/team-lead).
    can_view_all = is_admin or await has_global_permission(
        current_user, Permission.VIEW_ALL_ENGAGEMENTS, db
    )
    if not can_view_all:
        eng_query = (
            eng_query
            .join(EngagementAssignment, EngagementAssignment.engagement_id == Engagement.id)
            .where(EngagementAssignment.user_id == current_user.id)
        )
    eng_result = await db.execute(eng_query)
    engagements = eng_result.scalars().all()
    
    feed = []
    
    for me in manual_events:
        is_ooo = me.event_type == "OOO"

        # When filtering by user: show OOO events for those users, skip non-OOO events
        if filter_user_ids:
            if is_ooo and me.created_by in filter_user_ids:
                pass  # include this OOO event
            else:
                continue  # skip non-OOO events when filtering, and OOO for other users

        item = {
            "id": me.id,
            "title": me.title,
            "description": me.description,
            "start": me.start_time,
            "end": me.end_time,
            "type": "ooo" if is_ooo else "event",
            "color": "red" if is_ooo else "blue",
            "event_type": me.event_type,
            "created_by": me.created_by,
        }

        # Include creator info for OOO events
        if me.created_by_user:
            item["creator"] = {
                "id": me.created_by_user.id,
                "username": me.created_by_user.username,
                "full_name": me.created_by_user.full_name,
                "profile_photo": me.created_by_user.profile_photo,
            }

        feed.append(item)
        
    for eng in engagements:
        assigned = [
            {
                "id": u.id,
                "username": u.username,
                "full_name": u.full_name,
                "role": u.role
            } for u in eng.assigned_users
        ]
        # If filtering by users, only include engagements with matching users
        if filter_user_ids:
            if not any(u["id"] in filter_user_ids for u in assigned):
                continue

        # When phases with planned dates exist, emit one event per phase so the
        # calendar grid can color days by phase. Otherwise fall back to a single
        # event spanning the engagement's date range.
        phase_events = [
            p for p in (eng.phases or [])
            if p.planned_start and p.planned_end
            and p.planned_start <= end_naive and p.planned_end >= start_naive
        ]

        if phase_events:
            for p in sorted(phase_events, key=lambda x: x.sort_order):
                feed.append({
                    "id": f"{eng.id}:{p.id}",
                    "engagement_id": eng.id,
                    "title": f"{eng.name} ({eng.client_name})",
                    "description": eng.description,
                    "start": p.planned_start,
                    "end": p.planned_end,
                    "type": "engagement",
                    "color": "purple",
                    "status": eng.status,
                    "phase": p.phase_name,
                    "phase_sort_order": p.sort_order,
                    "engagement_start": eng.start_date,
                    "engagement_end": eng.end_date,
                    "assigned_users": assigned,
                })
        else:
            feed.append({
                "id": eng.id,
                "engagement_id": eng.id,
                "title": f"{eng.name} ({eng.client_name})",
                "description": eng.description,
                "start": eng.start_date,
                "end": eng.end_date,
                "type": "engagement",
                "color": "purple",
                "status": eng.status,
                "phase": None,
                "engagement_start": eng.start_date,
                "engagement_end": eng.end_date,
                "assigned_users": assigned,
            })

    return feed


@router.get("/team-availability")
async def get_team_availability(
    start: datetime = Query(...),
    end: datetime = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all active users with their engagement load for a date range."""
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        has_perm = await has_global_permission(current_user, Permission.CALENDAR_VIEW, db)
        if not has_perm:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions."
            )

    start_naive = start.replace(tzinfo=None) if start.tzinfo else start
    end_naive = end.replace(tzinfo=None) if end.tzinfo else end

    # Get all active users
    users_result = await db.execute(
        select(User).where(User.is_active == True).order_by(User.full_name, User.username)
    )
    all_users = users_result.scalars().all()

    # Get all engagements overlapping with the range
    eng_query = (
        select(Engagement)
        .options(selectinload(Engagement.assigned_users))
        .where(
            Engagement.start_date <= end_naive,
            or_(
                Engagement.end_date >= start_naive,
                Engagement.end_date.is_(None)
            )
        )
    )
    # GHSA-fpj5-2p59-xq8r: scope to assignments unless VIEW_ALL_ENGAGEMENTS.
    can_view_all = is_admin or await has_global_permission(
        current_user, Permission.VIEW_ALL_ENGAGEMENTS, db
    )
    if not can_view_all:
        eng_query = (
            eng_query
            .join(EngagementAssignment, EngagementAssignment.engagement_id == Engagement.id)
            .where(EngagementAssignment.user_id == current_user.id)
        )
    eng_result = await db.execute(eng_query)
    engagements = eng_result.scalars().all()

    # Get OOO events overlapping with the range
    ooo_query = select(CalendarEvent).where(
        CalendarEvent.event_type == "OOO",
        CalendarEvent.start_time <= end_naive,
        CalendarEvent.end_time >= start_naive
    )
    ooo_result = await db.execute(ooo_query)
    ooo_events = ooo_result.scalars().all()

    # Get all user skills
    skills_result = await db.execute(
        select(UserSkill)
        .options(selectinload(UserSkill.skill).selectinload(Skill.category))
    )
    all_user_skills = skills_result.scalars().all()
    user_skills_map: dict = {u.id: [] for u in all_users}
    for us in all_user_skills:
        if us.user_id in user_skills_map:
            user_skills_map[us.user_id].append({
                "skill_id": us.skill_id,
                "skill_name": us.skill.name,
                "category_id": us.skill.category_id,
                "category_name": us.skill.category.name,
                "level": us.level,
            })

    # Build user -> engagements map
    user_eng_map: dict = {u.id: [] for u in all_users}
    for eng in engagements:
        for u in eng.assigned_users:
            if u.id in user_eng_map:
                user_eng_map[u.id].append({
                    "id": eng.id,
                    "name": eng.name,
                    "client_name": eng.client_name,
                    "start_date": eng.start_date.isoformat() if eng.start_date else None,
                    "end_date": eng.end_date.isoformat() if eng.end_date else None,
                    "status": eng.status.value if hasattr(eng.status, 'value') else eng.status,
                    "engagement_type": eng.engagement_type,
                })

    # Build user -> OOO events map
    user_ooo_map: dict = {u.id: [] for u in all_users}
    for ooo in ooo_events:
        if ooo.created_by in user_ooo_map:
            user_ooo_map[ooo.created_by].append({
                "id": ooo.id,
                "title": ooo.title,
                "start_time": ooo.start_time.isoformat(),
                "end_time": ooo.end_time.isoformat(),
            })

    result = []
    for user in all_users:
        result.append({
            "user": {
                "id": user.id,
                "username": user.username,
                "full_name": user.full_name,
                "role": user.role.value if hasattr(user.role, 'value') else user.role,
                "profile_photo": user.profile_photo,
            },
            "engagements": user_eng_map.get(user.id, []),
            "engagement_count": len(user_eng_map.get(user.id, [])),
            "ooo_events": user_ooo_map.get(user.id, []),
            "user_skills": user_skills_map.get(user.id, []),
        })

    return result


@router.get("/auto-assign")
async def auto_assign_users(
    start: datetime = Query(...),
    end: datetime = Query(...),
    count: int = Query(3, ge=1, le=20),
    exclude_busy: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Suggest the most available users for a date range."""
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins and team leads can use auto-assign."
        )

    start_naive = start.replace(tzinfo=None) if start.tzinfo else start
    end_naive = end.replace(tzinfo=None) if end.tzinfo else end

    # Get all active users
    users_result = await db.execute(
        select(User).where(User.is_active == True)
    )
    all_users = users_result.scalars().all()

    # Get overlapping engagements with assigned users
    eng_query = (
        select(Engagement)
        .options(selectinload(Engagement.assigned_users))
        .where(
            Engagement.start_date <= end_naive,
            or_(
                Engagement.end_date >= start_naive,
                Engagement.end_date.is_(None)
            )
        )
    )
    eng_result = await db.execute(eng_query)
    engagements = eng_result.scalars().all()

    # Get OOO events overlapping with the range
    ooo_query = select(CalendarEvent).where(
        CalendarEvent.event_type == "OOO",
        CalendarEvent.start_time <= end_naive,
        CalendarEvent.end_time >= start_naive
    )
    ooo_result = await db.execute(ooo_query)
    ooo_events = ooo_result.scalars().all()

    # Build set of user IDs who have OOO during this period
    users_with_ooo = set()
    user_ooo_map: dict = {}
    for ooo in ooo_events:
        users_with_ooo.add(ooo.created_by)
        if ooo.created_by not in user_ooo_map:
            user_ooo_map[ooo.created_by] = []
        user_ooo_map[ooo.created_by].append({
            "id": ooo.id,
            "title": ooo.title,
            "start_time": ooo.start_time.isoformat(),
            "end_time": ooo.end_time.isoformat(),
        })

    # Count overlapping engagements per user
    user_overlap: dict = {u.id: [] for u in all_users}
    for eng in engagements:
        for u in eng.assigned_users:
            if u.id in user_overlap:
                user_overlap[u.id].append({
                    "id": eng.id,
                    "name": eng.name,
                    "client_name": eng.client_name,
                    "start_date": eng.start_date.isoformat() if eng.start_date else None,
                    "end_date": eng.end_date.isoformat() if eng.end_date else None,
                    "status": eng.status.value if hasattr(eng.status, 'value') else eng.status,
                })

    suggestions = []
    for user in all_users:
        overlapping = user_overlap.get(user.id, [])
        has_ooo = user.id in users_with_ooo

        # Skip users who are OOO or busy (when exclude_busy is set)
        if has_ooo:
            continue  # Always exclude OOO users from auto-assign
        if exclude_busy and len(overlapping) > 0:
            continue

        suggestions.append({
            "user": {
                "id": user.id,
                "username": user.username,
                "full_name": user.full_name,
                "role": user.role.value if hasattr(user.role, 'value') else user.role,
                "profile_photo": user.profile_photo,
            },
            "overlapping_count": len(overlapping),
            "engagements": overlapping,
            "ooo_events": user_ooo_map.get(user.id, []),
        })

    # Sort by fewest overlapping engagements
    suggestions.sort(key=lambda x: x["overlapping_count"])

    return suggestions[:count]
