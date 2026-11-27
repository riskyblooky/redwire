from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, or_, distinct, and_
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

    # Each block is one statement; counts come from GROUP BY / FILTER rather
    # than loading rows (this endpoint used to run ~25 queries one after
    # another and load every finding and test case of the caller's
    # engagements just to len() them).
    from models.discussion import ActivityLog
    from models.engagement_role import EngagementRole
    from models.notification import Notification
    from models.testcase import TestCase

    first_of_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    now = datetime.utcnow()
    open_statuses = [FindingStatus.OPEN, FindingStatus.IN_REVIEW]
    pending_cleanup_statuses = [CleanupArtifactStatus.PENDING, CleanupArtifactStatus.PARTIALLY_CLEANED]
    my_engagement_ids = select(EngagementAssignment.engagement_id).where(
        EngagementAssignment.user_id == current_user.id)

    # Active engagements, by status
    active_by_status = dict((await db.execute(_eng_filter(
        select(Engagement.status, func.count()).where(Engagement.status.in_(active_statuses))
        .group_by(Engagement.status),
        Engagement.id,
    ))).all())

    # Findings: every count below is a sum over (severity, status) groups
    resolved = func.count().filter(
        Finding.status.in_([FindingStatus.CLOSED, FindingStatus.VERIFIED, FindingStatus.REMEDIATED]),
        Finding.updated_at >= first_of_month,
    )
    groups = (await db.execute(_eng_filter(
        select(Finding.severity, Finding.status, func.count(), resolved)
        .group_by(Finding.severity, Finding.status)
    ))).all()
    by_severity: dict = {}
    by_status: dict = {}
    for sev, st, n, _r in groups:
        by_severity[sev] = by_severity.get(sev, 0) + n
        by_status[st] = by_status.get(st, 0) + n
    total_findings = sum(n for *_x, n, _r in groups)
    critical_findings = by_severity.get(Severity.CRITICAL, 0)
    resolved_this_month = sum(r for *_x, r in groups)

    colors = {
        "CRITICAL": "bg-red-500",
        "HIGH": "bg-orange-500",
        "MEDIUM": "bg-amber-500",
        "LOW": "bg-blue-500",
        "INFO": "bg-slate-500"
    }
    severity_breakdown = [{
        "severity": sev.value.capitalize(),
        "count": by_severity.get(sev, 0),
        "color": colors.get(sev.value, "bg-slate-500"),
    } for sev in Severity]
    status_breakdown = [{
        "status": fs.value,
        "label": fs.value.replace("_", " ").title(),
        "count": by_status.get(fs, 0),
    } for fs in FindingStatus]

    # Top Critical/High Open Findings
    top_rows = (await db.execute(_eng_filter(
        select(Finding, Engagement.name)
        .outerjoin(Engagement, Engagement.id == Finding.engagement_id)
        .where(
            Finding.severity.in_([Severity.CRITICAL, Severity.HIGH]),
            Finding.status.in_(open_statuses),
        )
        .order_by(desc(Finding.severity == Severity.CRITICAL), desc(Finding.created_at), Finding.id)
        .limit(5),
        Finding.engagement_id,
    ))).all()
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
        "engagement_name": None if strip_identifiers else eng_name,
        "created_at": f.created_at.isoformat() if f.created_at else None,
    } for f, eng_name in top_rows]

    # Pending cleanup: in scope, and on the caller's own engagements (a
    # subset of the scope — the scope is either all engagements or theirs).
    pending_cleanup, my_pending_cleanup = (await db.execute(_eng_filter(
        select(func.count(), func.count().filter(CleanupArtifact.engagement_id.in_(my_engagement_ids)))
        .where(CleanupArtifact.status.in_(pending_cleanup_statuses)),
        CleanupArtifact.engagement_id,
    ))).one()

    # My Active Engagements, with their counts and my role on each.
    # Already limited to the caller's assignments, so only the optional
    # engagement_id narrowing applies.
    finding_count = (select(func.count()).where(Finding.engagement_id == Engagement.id)
                     .correlate(Engagement).scalar_subquery())
    testcase_count = (select(func.count()).where(TestCase.engagement_id == Engagement.id)
                      .correlate(Engagement).scalar_subquery())
    my_eng_query = (
        select(Engagement, EngagementRole.name, finding_count, testcase_count)
        .join(EngagementAssignment, EngagementAssignment.engagement_id == Engagement.id)
        .outerjoin(EngagementRole, EngagementRole.id == EngagementAssignment.role_id)
        .where(
            EngagementAssignment.user_id == current_user.id,
            Engagement.status.in_(active_statuses)
        )
        .order_by(desc(Engagement.updated_at), Engagement.id)
        .limit(5)
    )
    if engagement_id:
        my_eng_query = my_eng_query.where(Engagement.id == engagement_id)
    my_engagements = [{
        "id": e.id,
        "name": e.name,
        "client_name": e.client_name,
        "status": e.status.value,
        "engagement_type": e.engagement_type,
        "start_date": e.start_date.isoformat() if e.start_date else None,
        "end_date": e.end_date.isoformat() if e.end_date else None,
        "finding_count": n_findings,
        "testcase_count": n_testcases,
        "user_role": role_name,
    } for e, role_name, n_findings, n_testcases in (await db.execute(my_eng_query)).all()]

    # Upcoming Engagements
    upcoming_cutoff = now + timedelta(days=14)
    upcoming_query = (
        select(Engagement)
        .where(
            Engagement.start_date > now,
            Engagement.start_date <= upcoming_cutoff,
            Engagement.status.in_([EngagementStatus.PLANNING, EngagementStatus.IN_PROGRESS])
        )
        .order_by(Engagement.start_date, Engagement.id)
        .limit(5)
    )
    upcoming_query = _eng_filter(upcoming_query, Engagement.id)
    upcoming_db = (await db.execute(upcoming_query)).scalars().all()
    upcoming_engagements = [{
        "id": None if strip_identifiers else e.id,
        "name": None if strip_identifiers else e.name,
        "client_name": None if strip_identifiers else e.client_name,
        "status": e.status.value,
        "start_date": e.start_date.isoformat() if e.start_date else None,
        "end_date": e.end_date.isoformat() if e.end_date else None,
    } for e in upcoming_db]

    # Recent Activity
    activity_query = (
        select(ActivityLog, User.full_name, User.username, Engagement.name)
        .outerjoin(User, User.id == ActivityLog.user_id)
        .outerjoin(Engagement, Engagement.id == ActivityLog.engagement_id)
        .order_by(desc(ActivityLog.created_at), ActivityLog.id)
        .limit(10)
    )
    activity_query = _eng_filter(activity_query, ActivityLog.engagement_id)
    activities = []
    for log, full_name, username, eng_name in (await db.execute(activity_query)).all():
        activities.append({
            "id": log.id,
            "type": log.resource_type,
            # action verb stays (it's a taxonomy, not an identifier); the
            # human-readable title + user + resource names are stripped
            # in global mode so the activity feed doesn't reveal what's
            # happening on other teams' engagements.
            "title": log.action if strip_identifiers else (log.details or log.action),
            "user": None if strip_identifiers else (
                (full_name or username) if log.user_id and username else "System"
            ),
            "time": log.created_at.isoformat(),
            "severity": None,
            "action": log.action,
            "resource_id": None if strip_identifiers else log.resource_id,
            "engagement_id": None if strip_identifiers else log.engagement_id,
            "engagement_name": None if strip_identifiers else eng_name,
            "resource_name": None if strip_identifiers else log.resource_name,
        })

    # Team utilization and the personal stats: one row of scalar subqueries.
    # The personal ones ignore the stats scope (they're about the caller)
    # but honour an engagement_id.
    assigned_q = _eng_filter(
        select(func.count(distinct(EngagementAssignment.user_id)))
        .join(Engagement, EngagementAssignment.engagement_id == Engagement.id)
        .join(User, EngagementAssignment.user_id == User.id)
        .where(Engagement.status.in_(active_statuses), User.role != "admin", User.is_active == True),
        Engagement.id,
    )
    my_active_q = (
        select(func.count()).select_from(EngagementAssignment)
        .join(Engagement, EngagementAssignment.engagement_id == Engagement.id)
        .where(EngagementAssignment.user_id == current_user.id, Engagement.status.in_(active_statuses))
    )
    my_findings_q = select(
        func.count().filter(Finding.status.in_(open_statuses)),
    ).where(Finding.created_by == current_user.id)
    my_month_q = select(func.count()).where(
        Finding.created_by == current_user.id, Finding.created_at >= first_of_month)
    my_tests_q = (
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
        my_active_q = my_active_q.where(Engagement.id == engagement_id)
        my_findings_q = my_findings_q.where(Finding.engagement_id == engagement_id)
        my_month_q = my_month_q.where(Finding.engagement_id == engagement_id)
        my_tests_q = my_tests_q.where(Engagement.id == engagement_id)
    unread_q = select(func.count()).where(
        Notification.user_id == current_user.id, Notification.is_read == False)  # always global
    total_operators_q = select(func.count(User.id)).where(User.role != "admin", User.is_active == True)
    (total_operators, assigned_operators, my_active_eng_count, my_open_findings,
     my_findings_this_month, my_pending_tests, my_unread_notifications) = (await db.execute(select(
        total_operators_q.scalar_subquery(), assigned_q.scalar_subquery(), my_active_q.scalar_subquery(),
        my_findings_q.scalar_subquery(), my_month_q.scalar_subquery(), my_tests_q.scalar_subquery(),
        unread_q.scalar_subquery(),
    ))).one()

    team_utilization = {
        "total_operators": total_operators,
        "assigned_operators": assigned_operators,
        "utilization_pct": round((assigned_operators / total_operators * 100) if total_operators > 0 else 0),
    }

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
            "total": sum(active_by_status.values()),
            "in_progress": active_by_status.get(EngagementStatus.IN_PROGRESS, 0),
            "planning": active_by_status.get(EngagementStatus.PLANNING, 0),
            "reporting": active_by_status.get(EngagementStatus.REPORTING, 0),
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
        "recent_activity": activities,
        "personal_stats": personal_stats,
        "engagement_id": engagement_id,  # Echo back for client verification
    }
