from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, delete as sa_delete
from typing import List, Optional
import logging
from database import get_db
from models.user import User, UserRole
from models.engagement import Engagement, EngagementStatus
from models.engagement_phase import EngagementPhase
from models.client import Client
from schemas.engagement import (
    EngagementCreate, EngagementUpdate, EngagementResponse,
    EngagementPhaseResponse, EngagementPhaseUpdate,
)
from auth.dependencies import get_current_user
from auth.rbac import can_modify_resource

from sqlalchemy.orm import selectinload
from models.associations import EngagementAssignment
from models.engagement_role import EngagementRole
from models.evidence import Evidence
from models.discussion import Thread
from schemas.evidence import EvidenceResponse
from fastapi import UploadFile, File, Form
import os
import uuid
from utils.storage import storage_service
from utils.uploads import safe_content_type
from utils.collaboration import create_activity_log, build_change_summary, compute_changes_dict, manager
from models.discussion import ResourceType
from auth.rbac import check_engagement_permission
from models.permission import Permission
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/engagements", tags=["engagements"])


# ── Helper: auto-create default phases ──────────────────────────
async def auto_create_default_phases(db: AsyncSession, engagement: Engagement):
    """Create SCOPING/PLANNING/IN_PROGRESS/REPORTING phases with dates
    evenly distributed across the engagement's date range."""
    start = engagement.start_date
    end = engagement.end_date
    if not start or not end:
        # If no dates, create phases without date ranges
        for phase_name, order in EngagementPhase.DEFAULT_PHASES:
            db.add(EngagementPhase(
                engagement_id=engagement.id,
                phase_name=phase_name,
                sort_order=order,
            ))
        return

    # Strip timezone info if present (asyncpg requires naive datetimes for DateTime columns)
    if start.tzinfo:
        start = start.replace(tzinfo=None)
    if end.tzinfo:
        end = end.replace(tzinfo=None)

    total_days = max((end - start).days, 4)  # at least 1 day per phase
    phase_count = len(EngagementPhase.DEFAULT_PHASES)
    days_per_phase = total_days / phase_count

    for phase_name, order in EngagementPhase.DEFAULT_PHASES:
        p_start = start + timedelta(days=int(order * days_per_phase))
        p_end = start + timedelta(days=int((order + 1) * days_per_phase))
        if order == phase_count - 1:
            p_end = end  # last phase extends to engagement end
        db.add(EngagementPhase(
            engagement_id=engagement.id,
            phase_name=phase_name,
            sort_order=order,
            planned_start=p_start,
            planned_end=p_end,
        ))


@router.get("", response_model=List[EngagementResponse])
async def get_engagements(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    skip: int = 0,
    limit: int = 100,
    include_proposed: bool = Query(False, description="Include PROPOSED engagements in results"),
):
    """Get engagements. Admins/Team Leads see all, others see assigned ones.
    PROPOSED engagements are excluded by default (they live on the Planning page)."""
    # TODO: replace this hardcoded role trio with a proper permission
    # (e.g. `engagement_view_proposed`) — see /proposed below.
    if include_proposed and current_user.role not in [
        UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD,
    ]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins and team leads can include proposed engagements",
        )

    query = select(Engagement).options(
        selectinload(Engagement.assigned_users),
        selectinload(Engagement.assignment_details).selectinload(EngagementAssignment.role),
        selectinload(Engagement.client).selectinload(Client.client_type),
        selectinload(Engagement.phases),
    )

    # Exclude PROPOSED unless explicitly requested
    if not include_proposed:
        query = query.where(Engagement.status != EngagementStatus.PROPOSED)
    
    if current_user.role not in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]:
        # Also include engagements from clients the user has been granted access to
        from routers.clients import get_accessible_client_ids
        accessible_client_ids = await get_accessible_client_ids(current_user.id, db)
        conditions = [Engagement.assigned_users.any(User.id == current_user.id)]
        if accessible_client_ids:
            conditions.append(Engagement.client_id.in_(accessible_client_ids))
        query = query.where(or_(*conditions))
    
    query = query.offset(skip).limit(limit).order_by(Engagement.created_at.desc())
    result = await db.execute(query)
    engagements = result.scalars().all()
    return engagements


@router.get("/proposed", response_model=List[EngagementResponse])
async def get_proposed_engagements(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get only PROPOSED engagements. Used by the Planning page."""
    # TODO: replace this hardcoded role trio with a proper permission
    # (e.g. `engagement_view_proposed`). The same gate is also inlined
    # for the `?include_proposed=true` query above and on the
    # /engagements page's "Show Proposed" toggle on the frontend.
    if current_user.role not in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins and team leads can view proposed engagements"
        )

    query = (
        select(Engagement)
        .options(
            selectinload(Engagement.assigned_users),
            selectinload(Engagement.assignment_details).selectinload(EngagementAssignment.role),
            selectinload(Engagement.client).selectinload(Client.client_type),
            selectinload(Engagement.phases),
        )
        .where(Engagement.status == EngagementStatus.PROPOSED)
        .order_by(Engagement.start_date.asc())
    )
    result = await db.execute(query)
    return result.scalars().all()

@router.get("/{engagement_id}", response_model=EngagementResponse)
async def get_engagement(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific engagement by ID. Admins/Team Leads see all, others see assigned ones."""
    result = await db.execute(
        select(Engagement)
        .options(
            selectinload(Engagement.assigned_users),
            selectinload(Engagement.assignment_details).selectinload(EngagementAssignment.role),
            selectinload(Engagement.client).selectinload(Client.client_type),
            selectinload(Engagement.phases),
        )
        .where(Engagement.id == engagement_id)
    )
    engagement = result.scalar_one_or_none()
    
    if not engagement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Engagement not found"
        )

    # Authorization Check using RBAC
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    
    if not is_admin:
        has_permission = await check_engagement_permission(current_user.id, engagement_id, Permission.ENGAGEMENT_VIEW.value, db)
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions. You need the 'engagement_view' permission to view this engagement."
            )
    
    return engagement

@router.post("", response_model=EngagementResponse, status_code=status.HTTP_201_CREATED)
async def create_engagement(
    engagement_data: EngagementCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new engagement."""
    if current_user.role not in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to create engagements"
        )
    
    data = engagement_data.model_dump()
    user_ids = data.pop("assigned_user_ids", [])
    assignments_data = data.pop("assignments", [])
    
    # Strip empty client_id to prevent UUID DataError
    if not data.get("client_id"):
        data["client_id"] = None
    
    # Auto-populate client_name from client_id if provided
    if data.get("client_id"):
        from models.client import Client
        client_result = await db.execute(select(Client).where(Client.id == data["client_id"]))
        client = client_result.scalar_one_or_none()
        if client:
            data["client_name"] = client.name
    
    # Strip timezone info from dates (asyncpg requires naive datetimes for DateTime columns)
    for date_field in ('start_date', 'end_date'):
        if data.get(date_field) and hasattr(data[date_field], 'tzinfo') and data[date_field].tzinfo:
            data[date_field] = data[date_field].replace(tzinfo=None)

    new_engagement = Engagement(
        **data,
        created_by=current_user.id
    )
    db.add(new_engagement)
    await db.flush() # Get ID

    # Handle assignments
    if assignments_data:
        for assign in assignments_data:
            new_assign = EngagementAssignment(
                engagement_id=new_engagement.id,
                user_id=assign["user_id"],
                role_id=assign["role_id"]
            )
            db.add(new_assign)
    elif user_ids:
        # Backward compatibility: assign with no specific role (or default if we had one)
        for uid in user_ids:
            new_assign = EngagementAssignment(
                engagement_id=new_engagement.id,
                user_id=uid
            )
            db.add(new_assign)
    
    db.add(new_engagement)
    await db.flush()  # Ensure engagement has an ID

    # Auto-create phases for non-PROPOSED engagements
    if new_engagement.status != EngagementStatus.PROPOSED:
        await auto_create_default_phases(db, new_engagement)

    await db.commit()
    await db.refresh(new_engagement)
    
    # Log activity
    await create_activity_log(
        db,
        engagement_id=new_engagement.id,
        user_id=current_user.id,
        action="created_engagement",
        resource_type="engagement",
        resource_id=new_engagement.id,
        resource_name=new_engagement.name,
        details=f"Engagement initialized: {new_engagement.name}"
    )

    # Reload with relationships
    return await get_engagement(new_engagement.id, db, current_user)

@router.put("/{engagement_id}", response_model=EngagementResponse)
async def update_engagement(
    engagement_id: str,
    engagement_data: EngagementUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update an engagement."""
    result = await db.execute(
        select(Engagement)
        .options(selectinload(Engagement.assigned_users))
        .where(Engagement.id == engagement_id)
    )
    engagement = result.scalar_one_or_none()
    
    if not engagement:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Engagement not found")
    
    # Check if user has permission to modify using RBAC
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    
    if not is_admin:
        has_permission = await check_engagement_permission(current_user.id, engagement_id, Permission.ENGAGEMENT_EDIT.value, db)
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions. You need the 'engagement_edit' permission to modify this engagement."
            )

    # GHSA-2gmw-jf4c-8q5g: COMPLETED is a terminal state. Once an engagement
    # is signed off, only admins / team-leads may modify any field, including
    # reopening the status — this blocks both post-signoff tampering and the
    # one-shot reopen-edit-recomplete cover-up.
    if engagement.status == EngagementStatus.COMPLETED and not is_admin:
        logger.warning(
            "Blocked update on COMPLETED engagement %s by user %s",
            engagement.id, current_user.id,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Engagement is locked: status is COMPLETED. Ask an administrator to reopen it before editing.",
        )

    update_data = engagement_data.model_dump(exclude_unset=True)
    user_ids = update_data.pop("assigned_user_ids", None)
    assignments_data = update_data.pop("assignments", None)

    # GHSA-rh65-78qj-3mg2: non-admin operators may not re-parent an engagement
    # to a different client via mass-assigned client_id. Admins/leads still can.
    if not is_admin:
        update_data.pop("client_id", None)

    # GHSA-2778-7vvg-h9x9: rewriting the engagement team is gated by a separate
    # permission; engagement_edit alone is not enough.
    if not is_admin and (user_ids is not None or assignments_data is not None):
        if not await check_engagement_permission(
            current_user.id, engagement_id, Permission.ENGAGEMENT_MANAGE_MEMBERS.value, db
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions. You need the 'engagement_manage_members' permission to change team membership.",
            )

    # Capture old status before applying updates (for notification)
    old_eng_status = engagement.status if engagement.status else None

    # Auto-populate client_name from client_id if provided
    if update_data.get("client_id"):
        from models.client import Client
        client_result = await db.execute(select(Client).where(Client.id == update_data["client_id"]))
        client_obj = client_result.scalar_one_or_none()
        if client_obj:
            update_data["client_name"] = client_obj.name
    
    # Capture old assigned user IDs BEFORE processing changes
    old_assigned_user_ids = set()
    if engagement.assigned_users:
        old_assigned_user_ids = {u.id for u in engagement.assigned_users}
    
    # Capture change summary before applying updates
    change_details = build_change_summary(engagement, update_data, label=f"Updated engagement '{engagement.name}'")
    # Structured changes for automation matching (GHSA-88hm follow-up).
    changes = compute_changes_dict(engagement, update_data)
    team_changed = assignments_data is not None or user_ids is not None
    if team_changed:
        change_details += ", team assignments updated"
    
    # Strip timezone info from dates (asyncpg requires naive datetimes for DateTime columns)
    for date_field in ('start_date', 'end_date'):
        if date_field in update_data and update_data[date_field] and hasattr(update_data[date_field], 'tzinfo') and update_data[date_field].tzinfo:
            update_data[date_field] = update_data[date_field].replace(tzinfo=None)

    for field, value in update_data.items():
        setattr(engagement, field, value)
    
    engagement.updated_by = current_user.id
    
    # Track new user IDs for notifications
    new_assigned_user_ids: set = set()
    
    if assignments_data is not None:
        # Remove old assignments
        await db.execute(
            select(EngagementAssignment).where(EngagementAssignment.engagement_id == engagement_id)
        )
        # We'll actually just delete them and recreate
        from sqlalchemy import delete
        await db.execute(delete(EngagementAssignment).where(EngagementAssignment.engagement_id == engagement_id))
        
        for assign in assignments_data:
            new_assign = EngagementAssignment(
                engagement_id=engagement_id,
                user_id=assign["user_id"],
                role_id=assign["role_id"]
            )
            db.add(new_assign)
            new_assigned_user_ids.add(assign["user_id"])
            
    elif user_ids is not None:
        # Backward compatibility
        from sqlalchemy import delete
        await db.execute(delete(EngagementAssignment).where(EngagementAssignment.engagement_id == engagement_id))
        for uid in user_ids:
            new_assign = EngagementAssignment(
                engagement_id=engagement_id,
                user_id=uid
            )
            db.add(new_assign)
            new_assigned_user_ids.add(uid)
    
    await db.commit()
    await db.refresh(engagement)

    # Auto-create phases when promoting from PROPOSED (and no phases exist yet)
    if (
        old_eng_status == EngagementStatus.PROPOSED
        and engagement.status != EngagementStatus.PROPOSED
    ):
        existing = await db.execute(
            select(EngagementPhase).where(EngagementPhase.engagement_id == engagement_id)
        )
        if not existing.scalars().first():
            await auto_create_default_phases(db, engagement)
            await db.commit()
    
    # Log activity
    await create_activity_log(
        db,
        engagement_id=engagement.id,
        user_id=current_user.id,
        action="updated_engagement",
        resource_type="engagement",
        resource_id=engagement.id,
        resource_name=engagement.name,
        details=change_details,
        extra_context={"changes": changes},
    )

    # Notify team if engagement status changed
    new_eng_status = engagement.status if engagement.status else None
    if "status" in engagement_data.model_dump(exclude_unset=True) and old_eng_status != new_eng_status:
        from utils.collaboration import notify_engagement_users
        await notify_engagement_users(
            db=db,
            engagement_id=engagement.id,
            event_type="engagement_status_changed",
            title=f"Engagement status changed: {engagement.name}",
            message=f"{current_user.full_name or current_user.username} changed status from {old_eng_status} to {new_eng_status}",
            link=f"/engagements/{engagement.id}",
            actor_id=current_user.id,
        )
        await db.commit()

    # Notify newly added team members via persistent notifications
    if team_changed:
        from utils.collaboration import create_notification
        truly_new = new_assigned_user_ids - old_assigned_user_ids - {current_user.id}
        for uid in truly_new:
            await create_notification(
                db=db,
                user_id=uid,
                event_type="engagement_assigned",
                title=f"Added to {engagement.name}",
                message=f"{current_user.full_name or current_user.username} added you to this engagement",
                link=f"/engagements/{engagement.id}",
                actor_id=current_user.id,
                engagement_id=engagement.id,
            )

        # Notify removed team members
        removed = old_assigned_user_ids - new_assigned_user_ids - {current_user.id}
        for uid in removed:
            await create_notification(
                db=db,
                user_id=uid,
                event_type="engagement_removed",
                title=f"Removed from {engagement.name}",
                message=f"{current_user.full_name or current_user.username} removed you from this engagement",
                actor_id=current_user.id,
                engagement_id=engagement.id,
            )

        if truly_new or removed:
            await db.commit()

    # Reload with relationships
    return await get_engagement(engagement_id, db, current_user)


@router.delete("/{engagement_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_engagement(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete an engagement."""
    result = await db.execute(select(Engagement).where(Engagement.id == engagement_id))
    engagement = result.scalar_one_or_none()
    
    if not engagement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Engagement not found"
        )
    
    # GHSA-9h56-fv6g-5x98: READ_ONLY_ADMIN must not delete engagements
    # (it would erase the audit trail of every action ever taken under them).
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.TEAM_LEAD]

    if not is_admin:
        has_permission = await check_engagement_permission(current_user.id, engagement_id, Permission.ENGAGEMENT_DELETE.value, db)
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions. You need the 'engagement_delete' permission to delete this engagement."
            )
    
    # Log activity before deletion
    engagement_name = engagement.name
    engagement_id_val = engagement.id
    await create_activity_log(
        db,
        engagement_id=engagement_id_val,
        user_id=current_user.id,
        action="deleted_engagement",
        resource_type="engagement",
        resource_id=engagement_id_val,
        resource_name=engagement_name,
        details=f"Deleted engagement: {engagement_name}"
    )

    await db.delete(engagement)
    await db.commit()
    
    return None

@router.get("/{engagement_id}/evidence", response_model=List[EvidenceResponse])
async def get_engagement_evidence(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all evidence associated with an engagement (direct or via findings)."""
    # Authorization logic same as get_engagement
    query = select(Engagement).where(Engagement.id == engagement_id)
    result = await db.execute(query)
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Engagement not found")
        
    # Check permissions
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        has_permission = await check_engagement_permission(current_user.id, engagement_id, Permission.ENGAGEMENT_VIEW.value, db)
        if not has_permission:
            raise HTTPException(status_code=403, detail="Insufficient permissions. You need the 'engagement_view' permission to view evidence.")

    # Fetch evidence: directly linked OR linked to any finding in this engagement
    # Fetch evidence: directly linked OR linked to any finding in this engagement
    from models.finding import Finding
    from models.testcase import TestCase
    
    # Subquery to count unresolved threads for evidence
    unresolved_subquery = (
        select(Thread.resource_id, func.count(Thread.id).label("count"))
        .where(
            and_(
                Thread.resource_type == "evidence",
                Thread.is_resolved == False
            )
        )
        .group_by(Thread.resource_id)
        .subquery()
    )

    evidence_query = (
        select(
            Evidence,
            func.coalesce(unresolved_subquery.c.count, 0).label("unresolved_count"),
            User.username,
            User.profile_photo,
            Finding.title.label("finding_title"),
            TestCase.title.label("testcase_title")
        )
        .outerjoin(unresolved_subquery, Evidence.id == unresolved_subquery.c.resource_id)
        .outerjoin(User, Evidence.created_by == User.id)
        .outerjoin(Finding, Evidence.finding_id == Finding.id)
        .outerjoin(TestCase, Evidence.testcase_id == TestCase.id)
        .where(
            (Evidence.engagement_id == engagement_id) | 
            (Evidence.finding_id.in_(select(Finding.id).where(Finding.engagement_id == engagement_id))) |
            (Evidence.testcase_id.in_(select(TestCase.id).where(TestCase.engagement_id == engagement_id)))
        )
        .order_by(Evidence.created_at.desc())
    )
    
    ev_result = await db.execute(evidence_query)
    rows = ev_result.all()
    
    # Combine evidence with count, username, and linked item titles
    results = []
    for evidence, count, username, profile_photo, finding_title, testcase_title in rows:
        evidence.unresolved_thread_count = count
        evidence.created_by_username = username
        evidence.created_by_profile_photo = profile_photo
        evidence.finding_title = finding_title
        evidence.testcase_title = testcase_title
        results.append(evidence)
        
    return results

@router.post("/{engagement_id}/evidence", response_model=EvidenceResponse)
async def upload_engagement_evidence(
    engagement_id: str,
    file: UploadFile = File(...),
    description: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Upload a general attachment for an engagement."""
    # Check if engagement exists and user has permission
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]
    if not is_admin:
        has_permission = await check_engagement_permission(current_user.id, engagement_id, Permission.EVIDENCE_CREATE.value, db)
        if not has_permission:
            raise HTTPException(status_code=403, detail="Insufficient permissions. You need the 'evidence_create' permission to upload to this engagement.")

    # Read file content
    content = await file.read()
    file_size = len(content)

    # Generate unique filename
    ext = os.path.splitext(file.filename)[1] if file.filename else ""
    storage_filename = f"{uuid.uuid4()}{ext}"

    # GHSA-h77m-pjqc-5cm3 follow-up: server-derived MIME, not the client's
    # Content-Type header. Same string is stored on MinIO and on the
    # Evidence row that the frontend reads for inline-preview decisions.
    safe_mime = safe_content_type(file.filename)

    # Upload to MinIO
    try:
        await storage_service.upload_file(content, storage_filename, content_type=safe_mime)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Storage failure: {str(e)}")

    # Create record
    new_evidence = Evidence(
        engagement_id=engagement_id,
        filename=storage_filename,
        original_filename=file.filename or "unknown",
        file_path=storage_filename,
        file_size=file_size,
        mime_type=safe_mime,
        description=description,
        created_by=current_user.id
    )
    
    db.add(new_evidence)
    await db.commit()
    await db.refresh(new_evidence)
    
    # Log activity
    await create_activity_log(
        db,
        engagement_id=engagement_id,
        user_id=current_user.id,
        action="uploaded",
        resource_type="evidence",
        resource_id=new_evidence.id,
        resource_name=new_evidence.original_filename,
        details=f"Uploaded engagement attachment: {new_evidence.original_filename}"
    )
    
    return new_evidence


@router.get("/{engagement_id}/my-permissions", response_model=List[str])
async def get_my_engagement_permissions(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get the current user's permissions for a specific engagement."""
    from auth.permissions import get_user_engagement_permissions
    
    # Admins and Team Leads have all permissions
    if current_user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]:
        # Return all engagement permissions
        return [perm.value for perm in Permission if perm.value.startswith(('engagement_', 'finding_', 'asset_', 'testcase_', 'evidence_', 'vault_'))]
    
    # Get user's permissions for this engagement
    permissions = await get_user_engagement_permissions(current_user.id, engagement_id, db)
    return permissions


# ── Phase endpoints ──────────────────────────────────────────────

@router.get("/{engagement_id}/phases", response_model=List[EngagementPhaseResponse])
async def get_engagement_phases(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get phases for an engagement."""
    result = await db.execute(
        select(EngagementPhase)
        .where(EngagementPhase.engagement_id == engagement_id)
        .order_by(EngagementPhase.sort_order)
    )
    return result.scalars().all()


@router.post("/{engagement_id}/phases/generate", response_model=List[EngagementPhaseResponse])
async def generate_engagement_phases(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate default phases for an existing engagement that has none."""
    if current_user.role not in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins and team leads can generate engagement phases"
        )

    # Verify engagement exists
    result = await db.execute(select(Engagement).where(Engagement.id == engagement_id))
    engagement = result.scalar_one_or_none()
    if not engagement:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Engagement not found")

    # Check if phases already exist
    existing = await db.execute(
        select(EngagementPhase).where(EngagementPhase.engagement_id == engagement_id)
    )
    if existing.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Phases already exist for this engagement"
        )

    await auto_create_default_phases(db, engagement)
    await db.commit()

    # Return the newly created phases
    result = await db.execute(
        select(EngagementPhase)
        .where(EngagementPhase.engagement_id == engagement_id)
        .order_by(EngagementPhase.sort_order)
    )
    return result.scalars().all()


@router.put("/{engagement_id}/phases", response_model=List[EngagementPhaseResponse])
async def update_engagement_phases(
    engagement_id: str,
    phases_data: List[EngagementPhaseUpdate],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Bulk-update phase dates for an engagement."""
    if current_user.role not in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins and team leads can modify engagement phases"
        )

    for phase_update in phases_data:
        result = await db.execute(
            select(EngagementPhase).where(
                EngagementPhase.id == phase_update.id,
                EngagementPhase.engagement_id == engagement_id,
            )
        )
        phase = result.scalar_one_or_none()
        if not phase:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Phase {phase_update.id} not found for this engagement"
            )
        if phase_update.planned_start is not None:
            dt = phase_update.planned_start
            phase.planned_start = dt.replace(tzinfo=None) if dt.tzinfo else dt
        if phase_update.planned_end is not None:
            dt = phase_update.planned_end
            phase.planned_end = dt.replace(tzinfo=None) if dt.tzinfo else dt

    await db.commit()

    # Return updated phases
    result = await db.execute(
        select(EngagementPhase)
        .where(EngagementPhase.engagement_id == engagement_id)
        .order_by(EngagementPhase.sort_order)
    )
    return result.scalars().all()


# ============ Engagement comparison ============

from schemas.client import EngagementCompareResponse, EngagementSummary  # noqa: E402


def _is_engagement_visible(engagement: Engagement, user: User) -> bool:
    if user.role in (UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD):
        return True
    return any(u.id == user.id for u in (engagement.assigned_users or []))


@router.get("/compare/summary", response_model=EngagementCompareResponse)
async def compare_engagements(
    a: str = Query(..., description="Engagement A id"),
    b: str = Query(..., description="Engagement B id"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Side-by-side metrics for two engagements + an aggregate delta (b - a).

    The delta covers totals only. Per-finding diff (which specific findings recurred,
    were resolved, or are net-new) is intentionally out of scope for this v1 — that
    needs a finding-fingerprint matcher we don't have yet.
    """
    if a == b:
        raise HTTPException(status_code=400, detail="Engagement A and B must be different")

    eng_result = await db.execute(
        select(Engagement)
        .where(Engagement.id.in_([a, b]))
        .options(selectinload(Engagement.assigned_users))
    )
    eng_map = {e.id: e for e in eng_result.scalars().all()}
    if a not in eng_map or b not in eng_map:
        raise HTTPException(status_code=404, detail="Engagement not found")

    for eng in (eng_map[a], eng_map[b]):
        if not _is_engagement_visible(eng, current_user):
            raise HTTPException(status_code=404, detail="Engagement not found")

    # Reuse the per-engagement aggregator from clients.py — call once per client_id
    # set and merge results so two engagements from different clients still work.
    from routers.clients import _build_engagement_summaries
    client_ids: set[str] = set()
    for eng in (eng_map[a], eng_map[b]):
        if eng.client_id:
            client_ids.add(eng.client_id)

    summaries: List[EngagementSummary] = []
    if client_ids:
        summaries = await _build_engagement_summaries(client_ids, db)

    by_id = {s.id: s for s in summaries}
    # Engagements without a client_id won't appear above — synthesise empty summaries.
    for eid in (a, b):
        if eid not in by_id:
            eng = eng_map[eid]
            by_id[eid] = EngagementSummary(
                id=eng.id,
                name=eng.name,
                status=eng.status.value if hasattr(eng.status, "value") else str(eng.status),
                engagement_type=eng.engagement_type,
                client_id=eng.client_id,
                client_name=eng.client_name,
                start_date=eng.start_date,
                end_date=eng.end_date,
            )

    sa, sb = by_id[a], by_id[b]
    sev_keys = set(sa.findings_by_severity) | set(sb.findings_by_severity)
    delta_severity = {
        k: sb.findings_by_severity.get(k, 0) - sa.findings_by_severity.get(k, 0)
        for k in sev_keys
    }
    delta = {
        "finding_count": sb.finding_count - sa.finding_count,
        "open_findings": sb.open_findings - sa.open_findings,
        "closed_findings": sb.closed_findings - sa.closed_findings,
        "by_severity": delta_severity,
        "mttr_days": (
            None if (sa.mttr_days is None or sb.mttr_days is None)
            else round(sb.mttr_days - sa.mttr_days, 2)
        ),
    }
    return EngagementCompareResponse(a=sa, b=sb, delta=delta)
