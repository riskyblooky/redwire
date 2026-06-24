from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, or_, distinct, and_
from sqlalchemy.orm import selectinload
from database import get_db
from models.engagement import Engagement, EngagementStatus
from models.finding import Finding, Severity, FindingStatus
from models.user import User
from models.cleanup_artifact import CleanupArtifact, CleanupArtifactStatus
from models.associations import EngagementAssignment
from auth.dependencies import get_current_user
from auth.rbac import apply_stats_scope, scope_to_assignments
from datetime import datetime, timedelta
from typing import Optional

router = APIRouter(prefix="/analytics", tags=["analytics"])

@router.get("/dashboard-stats")
async def get_dashboard_stats(
    engagement_id: Optional[str] = Query(None, description="Scope stats to a specific engagement"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get aggregated dashboard statistics. Pass engagement_id to scope to a single engagement."""
    active_statuses = [EngagementStatus.IN_PROGRESS, EngagementStatus.PLANNING, EngagementStatus.REPORTING]

    # Resolve scoping context up-front. For non-admin callers every aggregate
    # query below is restricted to engagements they're assigned to UNLESS the
    # admin has flipped STATS_SCOPE_MODE to "global" — in which case the
    # caller sees platform-wide counts but identifying fields are stripped
    # from list-shaped responses below (top_findings, upcoming_engagements,
    # recent_activity) to keep names from leaking.
    is_admin_effective, allowed_eng_subq, strip_identifiers = await apply_stats_scope(
        engagement_id, db, current_user
    )

    def _eng_filter(query, column=Finding.engagement_id):
        return scope_to_assignments(query, column, engagement_id, is_admin_effective, allowed_eng_subq)

    # Active engagements
    active_eng_query = _eng_filter(
        select(Engagement).where(Engagement.status.in_(active_statuses)),
        Engagement.id,
    )
    active_eng_result = await db.execute(active_eng_query)
    active_engagements = active_eng_result.scalars().all()
    
    # Finding Stats
    total_findings_query = _eng_filter(select(func.count(Finding.id)))
    total_findings = (await db.execute(total_findings_query)).scalar() or 0
    
    critical_findings_query = _eng_filter(
        select(func.count(Finding.id)).where(Finding.severity == Severity.CRITICAL)
    )
    critical_findings = (await db.execute(critical_findings_query)).scalar() or 0
    
    # Resolved this month
    first_of_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    resolved_query = _eng_filter(
        select(func.count(Finding.id)).where(
            (Finding.status.in_([FindingStatus.CLOSED, FindingStatus.VERIFIED, FindingStatus.REMEDIATED])) &
            (Finding.updated_at >= first_of_month)
        )
    )
    resolved_this_month = (await db.execute(resolved_query)).scalar() or 0

    # Severity Breakdown
    severity_breakdown = []
    colors = {
        "CRITICAL": "bg-red-500",
        "HIGH": "bg-orange-500",
        "MEDIUM": "bg-amber-500",
        "LOW": "bg-blue-500",
        "INFO": "bg-slate-500"
    }
    
    for sev in Severity:
        sev_query = _eng_filter(
            select(func.count(Finding.id)).where(Finding.severity == sev)
        )
        count = (await db.execute(sev_query)).scalar() or 0
        severity_breakdown.append({
            "severity": sev.value.capitalize(),
            "count": count,
            "color": colors.get(sev.value, "bg-slate-500")
        })

    # Findings by Status
    status_breakdown = []
    for fs in FindingStatus:
        fs_count = (await db.execute(
            _eng_filter(select(func.count(Finding.id)).where(Finding.status == fs))
        )).scalar() or 0
        status_breakdown.append({
            "status": fs.value,
            "label": fs.value.replace("_", " ").title(),
            "count": fs_count,
        })

    # Top Critical/High Open Findings
    top_findings_query = (
        select(Finding)
        .options(selectinload(Finding.engagement))
        .where(
            Finding.severity.in_([Severity.CRITICAL, Severity.HIGH]),
            Finding.status.in_([FindingStatus.OPEN, FindingStatus.IN_REVIEW])
        )
        .order_by(
            desc(Finding.severity == Severity.CRITICAL),
            desc(Finding.created_at)
        )
        .limit(5)
    )
    top_findings_query = _eng_filter(top_findings_query, Finding.engagement_id)
    top_findings_result = await db.execute(top_findings_query)
    top_findings_db = top_findings_result.scalars().all()
    top_findings = [{
        "id": f.id,
        # In global-mode stats for non-admins, strip identifying fields
        # so platform-wide counts don't leak finding titles / engagement
        # names across teams. Admins and engagement-scoped callers see
        # full data.
        "title": None if strip_identifiers else f.title,
        "severity": f.severity.value if f.severity else None,
        "status": f.status.value if f.status else None,
        "engagement_id": None if strip_identifiers else f.engagement_id,
        "engagement_name": None if strip_identifiers else (
            f.engagement.name if f.engagement else None
        ),
        "created_at": f.created_at.isoformat() if f.created_at else None,
    } for f in top_findings_db]

    # Pending Cleanup Items
    cleanup_query = select(func.count(CleanupArtifact.id)).where(
        CleanupArtifact.status.in_([
            CleanupArtifactStatus.PENDING,
            CleanupArtifactStatus.PARTIALLY_CLEANED
        ])
    )
    cleanup_query = _eng_filter(cleanup_query, CleanupArtifact.engagement_id)
    pending_cleanup = (await db.execute(cleanup_query)).scalar() or 0

    # My Active Engagements
    my_eng_query = (
        select(Engagement)
        .join(EngagementAssignment, EngagementAssignment.engagement_id == Engagement.id)
        .options(
            selectinload(Engagement.findings),
            selectinload(Engagement.testcases),
            selectinload(Engagement.assignment_details).selectinload(EngagementAssignment.role),
        )
        .where(
            EngagementAssignment.user_id == current_user.id,
            Engagement.status.in_(active_statuses)
        )
        .order_by(desc(Engagement.updated_at))
        .limit(5)
    )
    # `my_eng_query` is already filtered to the caller's EngagementAssignment
    # rows, so it's safe to apply only the optional engagement_id narrowing here.
    if engagement_id:
        my_eng_query = my_eng_query.where(Engagement.id == engagement_id)
    my_eng_result = await db.execute(my_eng_query)
    my_engagements_db = my_eng_result.unique().scalars().all()
    my_engagements = []
    for e in my_engagements_db:
        # Find current user's role on this engagement
        user_role = None
        if e.assignment_details:
            for ad in e.assignment_details:
                if ad.user_id == current_user.id and ad.role:
                    user_role = ad.role.name
                    break
        my_engagements.append({
            "id": e.id,
            "name": e.name,
            "client_name": e.client_name,
            "status": e.status.value,
            "engagement_type": e.engagement_type,
            "start_date": e.start_date.isoformat() if e.start_date else None,
            "end_date": e.end_date.isoformat() if e.end_date else None,
            "finding_count": len(e.findings) if e.findings else 0,
            "testcase_count": len(e.testcases) if e.testcases else 0,
            "user_role": user_role,
        })

    # Upcoming Engagements
    now = datetime.utcnow()
    upcoming_cutoff = now + timedelta(days=14)
    upcoming_query = (
        select(Engagement)
        .where(
            Engagement.start_date > now,
            Engagement.start_date <= upcoming_cutoff,
            Engagement.status.in_([EngagementStatus.PLANNING, EngagementStatus.IN_PROGRESS])
        )
        .order_by(Engagement.start_date)
        .limit(5)
    )
    upcoming_query = _eng_filter(upcoming_query, Engagement.id)
    upcoming_result = await db.execute(upcoming_query)
    upcoming_db = upcoming_result.scalars().all()
    upcoming_engagements = [{
        "id": None if strip_identifiers else e.id,
        "name": None if strip_identifiers else e.name,
        "client_name": None if strip_identifiers else e.client_name,
        "status": e.status.value,
        "start_date": e.start_date.isoformat() if e.start_date else None,
        "end_date": e.end_date.isoformat() if e.end_date else None,
    } for e in upcoming_db]

    # Team Utilization
    total_operators = (await db.execute(
        select(func.count(User.id)).where(User.role != "admin", User.is_active == True)
    )).scalar() or 0

    assigned_query = (
        select(func.count(distinct(EngagementAssignment.user_id)))
        .join(Engagement, EngagementAssignment.engagement_id == Engagement.id)
        .join(User, EngagementAssignment.user_id == User.id)
        .where(
            Engagement.status.in_(active_statuses),
            User.role != "admin",
            User.is_active == True
        )
    )
    assigned_query = _eng_filter(assigned_query, Engagement.id)
    assigned_operators = (await db.execute(assigned_query)).scalar() or 0

    team_utilization = {
        "total_operators": total_operators,
        "assigned_operators": assigned_operators,
        "utilization_pct": round((assigned_operators / total_operators * 100) if total_operators > 0 else 0),
    }

    # Recent Activity
    from models.discussion import ActivityLog
    
    activity_query = (
        select(ActivityLog)
        .options(selectinload(ActivityLog.user), selectinload(ActivityLog.engagement))
        .order_by(desc(ActivityLog.created_at))
        .limit(10)
    )
    activity_query = _eng_filter(activity_query, ActivityLog.engagement_id)

    activity_result = await db.execute(activity_query)
    activities_db = activity_result.scalars().all()
    
    activities = []
    for log in activities_db:
        activities.append({
            "id": log.id,
            "type": log.resource_type,
            # action verb stays (it's a taxonomy, not an identifier); the
            # human-readable title + user + resource names are stripped
            # in global mode so the activity feed doesn't reveal what's
            # happening on other teams' engagements.
            "title": log.action if strip_identifiers else (log.details or log.action),
            "user": None if strip_identifiers else (
                log.user.username if log.user else "System"
            ),
            "time": log.created_at.isoformat(),
            "severity": None,
            "action": log.action,
            "resource_id": None if strip_identifiers else log.resource_id,
            "engagement_id": None if strip_identifiers else log.engagement_id,
            "engagement_name": None if strip_identifiers else (
                log.engagement.name if log.engagement else None
            ),
            "resource_name": None if strip_identifiers else log.resource_name,
        })

    # Personalized Stats
    from models.testcase import TestCase
    from models.notification import Notification

    # 1. My active engagements count
    my_active_eng_query = (
        select(func.count(distinct(Engagement.id)))
        .join(EngagementAssignment, EngagementAssignment.engagement_id == Engagement.id)
        .where(
            EngagementAssignment.user_id == current_user.id,
            Engagement.status.in_(active_statuses),
        )
    )
    if engagement_id:
        my_active_eng_query = my_active_eng_query.where(Engagement.id == engagement_id)
    my_active_eng_count = (await db.execute(my_active_eng_query)).scalar() or 0

    # 2. My open findings
    my_open_query = select(func.count(Finding.id)).where(
        Finding.created_by == current_user.id,
        Finding.status.in_([FindingStatus.OPEN, FindingStatus.IN_REVIEW]),
    )
    if engagement_id:
        my_open_query = my_open_query.where(Finding.engagement_id == engagement_id)
    my_open_findings = (await db.execute(my_open_query)).scalar() or 0

    # 3. My pending test cases
    my_tests_query = (
        select(func.count(TestCase.id))
        .join(Engagement, TestCase.engagement_id == Engagement.id)
        .join(EngagementAssignment, EngagementAssignment.engagement_id == Engagement.id)
        .where(
            EngagementAssignment.user_id == current_user.id,
            Engagement.status.in_(active_statuses),
            TestCase.is_executed == False,
        )
    )
    if engagement_id:
        my_tests_query = my_tests_query.where(Engagement.id == engagement_id)
    my_pending_tests = (await db.execute(my_tests_query)).scalar() or 0

    # 4. Findings I created this month
    my_month_query = select(func.count(Finding.id)).where(
        Finding.created_by == current_user.id,
        Finding.created_at >= first_of_month,
    )
    if engagement_id:
        my_month_query = my_month_query.where(Finding.engagement_id == engagement_id)
    my_findings_this_month = (await db.execute(my_month_query)).scalar() or 0

    # 5. Pending cleanup items on my engagements
    my_cleanup_query = (
        select(func.count(CleanupArtifact.id))
        .join(Engagement, CleanupArtifact.engagement_id == Engagement.id)
        .join(EngagementAssignment, EngagementAssignment.engagement_id == Engagement.id)
        .where(
            EngagementAssignment.user_id == current_user.id,
            CleanupArtifact.status.in_([
                CleanupArtifactStatus.PENDING,
                CleanupArtifactStatus.PARTIALLY_CLEANED,
            ]),
        )
    )
    if engagement_id:
        my_cleanup_query = my_cleanup_query.where(Engagement.id == engagement_id)
    my_pending_cleanup = (await db.execute(my_cleanup_query)).scalar() or 0

    # 6. Unread notifications (not scoped — always global)
    my_unread_notifications = (await db.execute(
        select(func.count(Notification.id)).where(
            Notification.user_id == current_user.id,
            Notification.is_read == False,
        )
    )).scalar() or 0

    personal_stats = {
        "my_active_engagements": my_active_eng_count,
        "my_open_findings": my_open_findings,
        "my_pending_tests": my_pending_tests,
        "my_findings_this_month": my_findings_this_month,
        "my_pending_cleanup": my_pending_cleanup,
        "my_unread_notifications": my_unread_notifications,
    }

    return {
        "active_engagements": {
            "total": len(active_engagements),
            "in_progress": len([e for e in active_engagements if e.status == EngagementStatus.IN_PROGRESS]),
            "planning": len([e for e in active_engagements if e.status == EngagementStatus.PLANNING]),
            "reporting": len([e for e in active_engagements if e.status == EngagementStatus.REPORTING])
        },
        "findings": {
            "total": total_findings,
            "critical": critical_findings,
            "resolved_this_month": resolved_this_month,
            "severity_breakdown": severity_breakdown,
            "status_breakdown": status_breakdown,
        },
        "top_findings": top_findings,
        "pending_cleanup": pending_cleanup,
        "my_engagements": my_engagements,
        "upcoming_engagements": upcoming_engagements,
        "team_utilization": team_utilization,
        "recent_activity": activities[:10],
        "personal_stats": personal_stats,
        "engagement_id": engagement_id,  # Echo back for client verification
    }
