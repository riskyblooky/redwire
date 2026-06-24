from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, extract, case, literal_column
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from database import get_db
from models.user import User
from models.finding import Finding, Severity, FindingStatus
from models.engagement import Engagement, EngagementStatus
from models.evidence import Evidence
from models.testcase import TestCase
from models.cleanup_artifact import CleanupArtifact, CleanupArtifactStatus
from models.associations import EngagementAssignment
from models.discussion import ActivityLog
from auth.dependencies import get_current_user
from auth.rbac import apply_stats_scope, scope_to_assignments
import asyncio

router = APIRouter(prefix="/stats", tags=["stats"])


def _parse_date_range(start_date: str = None, end_date: str = None, days: int = None):
    """Helper to parse date range from query params."""
    if start_date and end_date:
        start = datetime.fromisoformat(start_date.replace('Z', '+00:00')).replace(tzinfo=None)
        end = datetime.fromisoformat(end_date.replace('Z', '+00:00')).replace(tzinfo=None)
        return start, end
    elif days:
        end = datetime.now(timezone.utc).replace(tzinfo=None)
        start = end - timedelta(days=days)
        return start, end
    return None, None


@router.get("/overview")
async def get_overview_stats(
    engagement_id: str = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get high-level overview statistics."""

    is_admin, allowed, strip_identifiers = await apply_stats_scope(engagement_id, db, current_user)

    # Base queries — evidence joins through Finding so engagement scoping
    # can be applied on Finding.engagement_id uniformly.
    findings_query = select(func.count(Finding.id))
    engagements_query = select(func.count(Engagement.id))
    active_engagements_query = select(func.count(Engagement.id)).where(
        Engagement.status.in_([EngagementStatus.PLANNING, EngagementStatus.IN_PROGRESS])
    )
    evidence_query = select(func.count(Evidence.id)).join(
        Finding, Evidence.finding_id == Finding.id
    )
    critical_high_query = select(func.count(Finding.id)).where(
        Finding.severity.in_([Severity.CRITICAL, Severity.HIGH])
    )

    # Avg CVSS
    avg_cvss_query = select(func.avg(Finding.cvss_score)).where(Finding.cvss_score.isnot(None))

    # Active users (users who created findings/engagements in last 30 days)
    thirty_days_ago = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30)
    user_activity_query = select(func.count(func.distinct(Finding.created_by))).where(
        Finding.created_at >= thirty_days_ago
    )

    # Total team members
    total_users_query = select(func.count(User.id)).where(User.is_active == True)

    # Apply engagement scoping
    findings_query = scope_to_assignments(findings_query, Finding.engagement_id, engagement_id, is_admin, allowed)
    engagements_query = scope_to_assignments(engagements_query, Engagement.id, engagement_id, is_admin, allowed)
    active_engagements_query = scope_to_assignments(active_engagements_query, Engagement.id, engagement_id, is_admin, allowed)
    evidence_query = scope_to_assignments(evidence_query, Finding.engagement_id, engagement_id, is_admin, allowed)
    critical_high_query = scope_to_assignments(critical_high_query, Finding.engagement_id, engagement_id, is_admin, allowed)
    avg_cvss_query = scope_to_assignments(avg_cvss_query, Finding.engagement_id, engagement_id, is_admin, allowed)
    user_activity_query = scope_to_assignments(user_activity_query, Finding.engagement_id, engagement_id, is_admin, allowed)
    
    # Run queries sequentially (AsyncSession uses a single connection, not concurrency-safe)
    total_findings = (await db.execute(findings_query)).scalar()
    total_engagements = (await db.execute(engagements_query)).scalar()
    active_engagements = (await db.execute(active_engagements_query)).scalar()
    total_evidence = (await db.execute(evidence_query)).scalar()
    critical_high_findings = (await db.execute(critical_high_query)).scalar()
    avg_cvss = (await db.execute(avg_cvss_query)).scalar()
    active_users = (await db.execute(user_activity_query)).scalar()
    total_users = (await db.execute(total_users_query)).scalar()
    
    return {
        "total_findings": total_findings,
        "total_engagements": total_engagements,
        "active_engagements": active_engagements,
        "total_evidence": total_evidence,
        "critical_high_findings": critical_high_findings,
        "active_users": active_users,
        "total_users": total_users,
        "avg_cvss": round(avg_cvss, 1) if avg_cvss else 0,
    }


@router.get("/findings-timeline")
async def get_findings_timeline(
    days: int = None,
    start_date: str = None,
    end_date: str = None,
    engagement_id: str = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get findings created over time (grouped by day)."""

    is_admin, allowed, strip_identifiers = await apply_stats_scope(engagement_id, db, current_user)

    # Determine date range
    if start_date and end_date:
        start = datetime.fromisoformat(start_date.replace('Z', '+00:00')).replace(tzinfo=None)
        end = datetime.fromisoformat(end_date.replace('Z', '+00:00')).replace(tzinfo=None)
    elif days:
        start = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
        end = datetime.now(timezone.utc).replace(tzinfo=None)
    else:
        start = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30)
        end = datetime.now(timezone.utc).replace(tzinfo=None)

    # Group findings by date
    date_col = func.date_trunc('day', Finding.created_at).label('date')

    query = select(
        date_col,
        func.count(Finding.id).label('count')
    ).where(Finding.created_at >= start, Finding.created_at <= end)

    query = scope_to_assignments(query, Finding.engagement_id, engagement_id, is_admin, allowed)

    result = await db.execute(
        query.group_by(date_col)
        .order_by(date_col)
    )
    
    timeline_data = [
        {
            "date": row.date.strftime("%Y-%m-%d"),
            "count": row.count
        }
        for row in result.all()
    ]
    
    return {"timeline": timeline_data, "start_date": start.isoformat(), "end_date": end.isoformat()}


@router.get("/severity-distribution")
async def get_severity_distribution(
    start_date: str = None,
    end_date: str = None,
    engagement_id: str = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get distribution of findings by severity."""

    is_admin, allowed, strip_identifiers = await apply_stats_scope(engagement_id, db, current_user)

    query = select(
        Finding.severity,
        func.count(Finding.id).label('count')
    ).group_by(Finding.severity)

    # Apply date filtering if provided
    if start_date and end_date:
        start = datetime.fromisoformat(start_date.replace('Z', '+00:00')).replace(tzinfo=None)
        end = datetime.fromisoformat(end_date.replace('Z', '+00:00')).replace(tzinfo=None)
        query = query.where(Finding.created_at >= start, Finding.created_at <= end)

    query = scope_to_assignments(query, Finding.engagement_id, engagement_id, is_admin, allowed)

    result = await db.execute(query)
    
    distribution = [
        {
            "severity": row.severity.value,
            "count": row.count
        }
        for row in result.all()
    ]
    
    return {"distribution": distribution}


@router.get("/user-activity")
async def get_user_activity(
    start_date: str = None,
    end_date: str = None,
    engagement_id: str = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get top contributors by all activity log entries (excluding note auto-saves)."""

    is_admin, allowed, strip_identifiers = await apply_stats_scope(engagement_id, db, current_user)

    query = select(
        User.username,
        User.full_name,
        User.profile_photo,
        User.role,
        func.count(ActivityLog.id).label('activity_count'),
    ).join(ActivityLog, ActivityLog.user_id == User.id).where(
        # Exclude note auto-save activity since it fires every few seconds
        ActivityLog.action != 'updated_note'
    )

    if start_date and end_date:
        start = datetime.fromisoformat(start_date.replace('Z', '+00:00')).replace(tzinfo=None)
        end = datetime.fromisoformat(end_date.replace('Z', '+00:00')).replace(tzinfo=None)
        query = query.where(ActivityLog.created_at >= start, ActivityLog.created_at <= end)

    query = scope_to_assignments(query, ActivityLog.engagement_id, engagement_id, is_admin, allowed)

    query = query.group_by(
        User.id, User.username, User.full_name, User.profile_photo, User.role
    ).order_by(func.count(ActivityLog.id).desc()).limit(10)

    result = await db.execute(query)

    activity = [
        {
            # In global-mode stats for non-admins, drop the per-user
            # identifiers so the top-contributors list shows role and
            # activity count only — useful for org-wide pulse without
            # naming specific operators.
            "username": None if strip_identifiers else row.username,
            "full_name": None if strip_identifiers else row.full_name,
            "profile_photo": None if strip_identifiers else row.profile_photo,
            "role": row.role.value,
            "activity_count": row.activity_count,
        }
        for row in result.all()
    ]

    return {"top_contributors": activity}


@router.get("/engagement-status")
async def get_engagement_status(
    start_date: str = None,
    end_date: str = None,
    engagement_id: str = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get distribution of engagements by status."""

    is_admin, allowed, strip_identifiers = await apply_stats_scope(engagement_id, db, current_user)

    query = select(
        Engagement.status,
        func.count(Engagement.id).label('count')
    ).group_by(Engagement.status)

    # Apply date filtering if provided
    if start_date and end_date:
        start = datetime.fromisoformat(start_date.replace('Z', '+00:00')).replace(tzinfo=None)
        end = datetime.fromisoformat(end_date.replace('Z', '+00:00')).replace(tzinfo=None)
        query = query.where(Engagement.created_at >= start, Engagement.created_at <= end)

    query = scope_to_assignments(query, Engagement.id, engagement_id, is_admin, allowed)

    result = await db.execute(query)
    
    distribution = [
        {
            "status": row.status.value,
            "count": row.count
        }
        for row in result.all()
    ]
    
    return {"distribution": distribution}


# ──────────────────────────────────────────────────────────────
# NEW STATS ENDPOINTS
# ──────────────────────────────────────────────────────────────

@router.get("/findings-by-category")
async def get_findings_by_category(
    start_date: str = None,
    end_date: str = None,
    engagement_id: str = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get distribution of findings by category."""
    is_admin, allowed, strip_identifiers = await apply_stats_scope(engagement_id, db, current_user)

    query = select(
        func.coalesce(Finding.category, 'Uncategorized').label('category'),
        func.count(Finding.id).label('count')
    ).group_by(Finding.category)

    start, end = _parse_date_range(start_date, end_date)
    if start and end:
        query = query.where(Finding.created_at >= start, Finding.created_at <= end)
    query = scope_to_assignments(query, Finding.engagement_id, engagement_id, is_admin, allowed)

    query = query.order_by(func.count(Finding.id).desc()).limit(15)
    result = await db.execute(query)

    return {"categories": [{"category": r.category, "count": r.count} for r in result.all()]}


@router.get("/findings-by-status")
async def get_findings_by_status(
    start_date: str = None,
    end_date: str = None,
    engagement_id: str = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get distribution of findings by status."""
    is_admin, allowed, strip_identifiers = await apply_stats_scope(engagement_id, db, current_user)

    query = select(
        Finding.status,
        func.count(Finding.id).label('count')
    ).group_by(Finding.status)

    start, end = _parse_date_range(start_date, end_date)
    if start and end:
        query = query.where(Finding.created_at >= start, Finding.created_at <= end)
    query = scope_to_assignments(query, Finding.engagement_id, engagement_id, is_admin, allowed)

    result = await db.execute(query)

    return {"statuses": [{"status": r.status.value, "count": r.count} for r in result.all()]}


@router.get("/engagement-types")
async def get_engagement_types(
    start_date: str = None,
    end_date: str = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get distribution of engagements by type."""
    is_admin, allowed, strip_identifiers = await apply_stats_scope(None, db, current_user)

    query = select(
        Engagement.engagement_type,
        func.count(Engagement.id).label('count')
    ).group_by(Engagement.engagement_type)

    start, end = _parse_date_range(start_date, end_date)
    if start and end:
        query = query.where(Engagement.created_at >= start, Engagement.created_at <= end)
    query = scope_to_assignments(query, Engagement.id, None, is_admin, allowed)

    query = query.order_by(func.count(Engagement.id).desc())
    result = await db.execute(query)

    return {"types": [{"type": r.engagement_type, "count": r.count} for r in result.all()]}


@router.get("/engagement-metrics")
async def get_engagement_metrics(
    start_date: str = None,
    end_date: str = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get aggregate engagement metrics: avg duration, findings per engagement, avg CVSS per engagement, by client."""

    is_admin, allowed, strip_identifiers = await apply_stats_scope(None, db, current_user)
    start, end = _parse_date_range(start_date, end_date)

    # Avg duration of completed engagements (in days)
    dur_query = select(
        func.avg(
            extract('epoch', Engagement.end_date) - extract('epoch', Engagement.start_date)
        ).label('avg_seconds')
    ).where(
        Engagement.start_date.isnot(None),
        Engagement.end_date.isnot(None)
    )
    if start and end:
        dur_query = dur_query.where(Engagement.created_at >= start, Engagement.created_at <= end)
    dur_query = scope_to_assignments(dur_query, Engagement.id, None, is_admin, allowed)
    dur_result = await db.execute(dur_query)
    avg_seconds = dur_result.scalar()
    avg_duration_days = round(avg_seconds / 86400, 1) if avg_seconds else 0

    # Findings per engagement
    fpe_query = select(
        Engagement.name.label('engagement'),
        Engagement.client_name.label('client'),
        func.count(Finding.id).label('findings_count'),
        func.avg(Finding.cvss_score).label('avg_cvss')
    ).outerjoin(Finding, Finding.engagement_id == Engagement.id).group_by(
        Engagement.id, Engagement.name, Engagement.client_name
    ).order_by(func.count(Finding.id).desc()).limit(20)

    if start and end:
        fpe_query = fpe_query.where(Engagement.created_at >= start, Engagement.created_at <= end)
    fpe_query = scope_to_assignments(fpe_query, Engagement.id, None, is_admin, allowed)

    fpe_result = await db.execute(fpe_query)
    per_engagement = [
        {
            # Engagement + client names stripped in global mode for non-admins
            # so platform-wide leaderboards don't reveal who's the customer.
            "engagement": None if strip_identifiers else r.engagement,
            "client": None if strip_identifiers else r.client,
            "findings_count": r.findings_count,
            "avg_cvss": round(r.avg_cvss, 1) if r.avg_cvss else 0
        }
        for r in fpe_result.all()
    ]

    # Engagements by client
    client_query = select(
        Engagement.client_name.label('client'),
        func.count(Engagement.id).label('count')
    ).group_by(Engagement.client_name).order_by(func.count(Engagement.id).desc()).limit(10)
    if start and end:
        client_query = client_query.where(Engagement.created_at >= start, Engagement.created_at <= end)
    client_query = scope_to_assignments(client_query, Engagement.id, None, is_admin, allowed)
    client_result = await db.execute(client_query)
    by_client = [
        {
            "client": None if strip_identifiers else r.client,
            "count": r.count,
        }
        for r in client_result.all()
    ]

    return {
        "avg_duration_days": avg_duration_days,
        "per_engagement": per_engagement,
        "by_client": by_client,
    }


@router.get("/operator-performance")
async def get_operator_performance(
    start_date: str = None,
    end_date: str = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Per-operator breakdown: findings by severity, engagement count, test cases executed."""

    is_admin, allowed, strip_identifiers = await apply_stats_scope(None, db, current_user)
    start, end = _parse_date_range(start_date, end_date)

    # Per-user findings with severity breakdown
    severity_cases = {
        sev: func.count(case((Finding.severity == sev, Finding.id))).label(sev.value.lower())
        for sev in Severity
    }

    findings_query = select(
        User.id.label('user_id'),
        User.username,
        User.full_name,
        User.profile_photo,
        User.role,
        User.last_active,
        func.count(Finding.id).label('total_findings'),
        *severity_cases.values(),
    ).outerjoin(Finding, Finding.created_by == User.id).where(User.is_active == True)

    if start and end:
        findings_query = findings_query.where(
            (Finding.created_at >= start) | (Finding.created_at.is_(None)),
            (Finding.created_at <= end) | (Finding.created_at.is_(None)),
        )

    findings_query = findings_query.group_by(
        User.id, User.username, User.full_name, User.profile_photo, User.role, User.last_active
    )
    findings_query = scope_to_assignments(findings_query, Finding.engagement_id, None, is_admin, allowed)
    findings_result = await db.execute(findings_query)
    user_findings = {r.user_id: r for r in findings_result.all()}

    # Engagements per user
    eng_query = select(
        EngagementAssignment.user_id,
        func.count(EngagementAssignment.engagement_id).label('engagement_count')
    ).group_by(EngagementAssignment.user_id)
    eng_query = scope_to_assignments(eng_query, EngagementAssignment.engagement_id, None, is_admin, allowed)
    eng_result = await db.execute(eng_query)
    user_engs = {r.user_id: r.engagement_count for r in eng_result.all()}

    # Test cases executed per user
    tc_query = select(
        TestCase.created_by,
        func.count(TestCase.id).label('total'),
        func.count(case((TestCase.is_executed == True, TestCase.id))).label('executed'),
        func.count(case((TestCase.is_successful == True, TestCase.id))).label('successful'),
    ).group_by(TestCase.created_by)
    if start and end:
        tc_query = tc_query.where(TestCase.created_at >= start, TestCase.created_at <= end)
    tc_query = scope_to_assignments(tc_query, TestCase.engagement_id, None, is_admin, allowed)
    tc_result = await db.execute(tc_query)
    user_tc = {r.created_by: r for r in tc_result.all()}

    operators = []
    for uid, f in user_findings.items():
        tc = user_tc.get(uid)
        operators.append({
            # Per-operator identity stripped in global mode for non-admins —
            # role + counts give an aggregate view without naming people.
            "user_id": None if strip_identifiers else uid,
            "username": None if strip_identifiers else f.username,
            "full_name": None if strip_identifiers else f.full_name,
            "profile_photo": None if strip_identifiers else f.profile_photo,
            "role": f.role.value if f.role else "operator",
            "last_active": f.last_active.isoformat() if f.last_active else None,
            "total_findings": f.total_findings,
            "critical": f.critical,
            "high": f.high,
            "medium": f.medium,
            "low": f.low,
            "info": f.info,
            "engagement_count": user_engs.get(uid, 0),
            "testcases_total": tc.total if tc else 0,
            "testcases_executed": tc.executed if tc else 0,
            "testcases_successful": tc.successful if tc else 0,
        })

    # Sort by total findings desc
    operators.sort(key=lambda x: x['total_findings'], reverse=True)

    return {"operators": operators}


@router.get("/testcase-stats")
async def get_testcase_stats(
    start_date: str = None,
    end_date: str = None,
    engagement_id: str = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get test case execution and success rates."""

    is_admin, allowed, strip_identifiers = await apply_stats_scope(engagement_id, db, current_user)
    start, end = _parse_date_range(start_date, end_date)

    base = select(
        func.count(TestCase.id).label('total'),
        func.count(case((TestCase.is_executed == True, TestCase.id))).label('executed'),
        func.count(case((TestCase.is_successful == True, TestCase.id))).label('successful'),
    )
    if start and end:
        base = base.where(TestCase.created_at >= start, TestCase.created_at <= end)
    base = scope_to_assignments(base, TestCase.engagement_id, engagement_id, is_admin, allowed)

    result = await db.execute(base)
    row = result.one()

    # By category
    cat_query = select(
        TestCase.category,
        func.count(TestCase.id).label('total'),
        func.count(case((TestCase.is_executed == True, TestCase.id))).label('executed'),
        func.count(case((TestCase.is_successful == True, TestCase.id))).label('successful'),
    ).group_by(TestCase.category).order_by(func.count(TestCase.id).desc())
    if start and end:
        cat_query = cat_query.where(TestCase.created_at >= start, TestCase.created_at <= end)
    cat_query = scope_to_assignments(cat_query, TestCase.engagement_id, engagement_id, is_admin, allowed)
    cat_result = await db.execute(cat_query)

    return {
        "total": row.total,
        "executed": row.executed,
        "successful": row.successful,
        "execution_rate": round(row.executed / row.total * 100, 1) if row.total else 0,
        "success_rate": round(row.successful / row.executed * 100, 1) if row.executed else 0,
        "by_category": [
            {
                "category": r.category,
                "total": r.total,
                "executed": r.executed,
                "successful": r.successful,
            }
            for r in cat_result.all()
        ],
    }


@router.get("/cleanup-stats")
async def get_cleanup_stats(
    start_date: str = None,
    end_date: str = None,
    engagement_id: str = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get cleanup artifact status distribution."""

    is_admin, allowed, strip_identifiers = await apply_stats_scope(engagement_id, db, current_user)
    start, end = _parse_date_range(start_date, end_date)

    query = select(
        CleanupArtifact.status,
        func.count(CleanupArtifact.id).label('count')
    ).group_by(CleanupArtifact.status)

    if start and end:
        query = query.where(CleanupArtifact.created_at >= start, CleanupArtifact.created_at <= end)
    query = scope_to_assignments(query, CleanupArtifact.engagement_id, engagement_id, is_admin, allowed)

    result = await db.execute(query)

    total_query = select(func.count(CleanupArtifact.id))
    if start and end:
        total_query = total_query.where(CleanupArtifact.created_at >= start, CleanupArtifact.created_at <= end)
    total_query = scope_to_assignments(total_query, CleanupArtifact.engagement_id, engagement_id, is_admin, allowed)
    total_result = await db.execute(total_query)
    total = total_result.scalar()

    return {
        "total": total,
        "distribution": [{"status": r.status.value, "count": r.count} for r in result.all()],
    }


@router.get("/client-stats")
async def get_client_stats(
    start_date: str = None,
    end_date: str = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get comprehensive per-client statistics."""

    is_admin, allowed, strip_identifiers = await apply_stats_scope(None, db, current_user)
    start, end = _parse_date_range(start_date, end_date)

    # ── Per-client engagement count, avg duration ──
    eng_query = select(
        Engagement.client_name.label('client'),
        func.count(Engagement.id).label('engagement_count'),
        func.avg(
            extract('epoch', Engagement.end_date) - extract('epoch', Engagement.start_date)
        ).label('avg_seconds'),
    ).where(
        Engagement.client_name.isnot(None),
        Engagement.start_date.isnot(None),
        Engagement.end_date.isnot(None),
    ).group_by(Engagement.client_name)

    if start and end:
        eng_query = eng_query.where(Engagement.created_at >= start, Engagement.created_at <= end)
    eng_query = scope_to_assignments(eng_query, Engagement.id, None, is_admin, allowed)

    eng_result = await db.execute(eng_query)
    client_eng = {r.client: r for r in eng_result.all()}

    # ── Per-client engagement types ──
    type_query = select(
        Engagement.client_name.label('client'),
        Engagement.engagement_type,
        func.count(Engagement.id).label('cnt'),
    ).where(Engagement.client_name.isnot(None)).group_by(
        Engagement.client_name, Engagement.engagement_type
    )
    if start and end:
        type_query = type_query.where(Engagement.created_at >= start, Engagement.created_at <= end)
    type_query = scope_to_assignments(type_query, Engagement.id, None, is_admin, allowed)
    type_result = await db.execute(type_query)
    client_types: dict = {}
    for r in type_result.all():
        client_types.setdefault(r.client, []).append({"type": r.engagement_type, "count": r.cnt})

    # ── Per-client findings with severity breakdown ──
    severity_cases = {
        sev: func.count(case((Finding.severity == sev, Finding.id))).label(sev.value.lower())
        for sev in Severity
    }

    findings_query = select(
        Engagement.client_name.label('client'),
        func.count(Finding.id).label('total_findings'),
        func.avg(Finding.cvss_score).label('avg_cvss'),
        *severity_cases.values(),
    ).join(Finding, Finding.engagement_id == Engagement.id).where(
        Engagement.client_name.isnot(None)
    ).group_by(Engagement.client_name)

    if start and end:
        findings_query = findings_query.where(Finding.created_at >= start, Finding.created_at <= end)
    findings_query = scope_to_assignments(findings_query, Engagement.id, None, is_admin, allowed)

    findings_result = await db.execute(findings_query)
    client_findings = {r.client: r for r in findings_result.all()}

    # ── Merge ──
    all_clients = set(client_eng.keys()) | set(client_findings.keys())
    clients = []
    for client in sorted(all_clients):
        e = client_eng.get(client)
        f = client_findings.get(client)
        avg_seconds = e.avg_seconds if e else None
        clients.append({
            # Client name stripped in global mode for non-admins. The page
            # remains usable as a platform-wide volume view (engagement
            # count, findings, avg CVSS) without naming customers.
            "client": None if strip_identifiers else client,
            "engagement_count": e.engagement_count if e else 0,
            "avg_duration_days": round(avg_seconds / 86400, 1) if avg_seconds else 0,
            "total_findings": f.total_findings if f else 0,
            "critical": f.critical if f else 0,
            "high": f.high if f else 0,
            "medium": f.medium if f else 0,
            "low": f.low if f else 0,
            "info": f.info if f else 0,
            "avg_cvss": round(f.avg_cvss, 1) if f and f.avg_cvss else 0,
            "engagement_types": client_types.get(client, []),
        })

    # Sort by total findings desc
    clients.sort(key=lambda x: x['total_findings'], reverse=True)

    return {"clients": clients}
