"""
Dashboard Widgets router — CRUD for widget definitions + user layout management.
Includes advanced custom query builder with JOINs, date-range filtering,
time-series bucketing, and multi-series support.
"""

import logging
from typing import Optional, List
from datetime import datetime, timedelta
from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func, and_, cast, Float, Integer, String as SAString, case, extract, text

from database import get_db
from models.user import User, UserRole
from models.dashboard_widget import DashboardWidget
from models.permission import Permission
from models.finding import Finding, Severity, FindingStatus
from models.engagement import Engagement, EngagementStatus
from models.asset import Asset
from models.testcase import TestCase
from models.cleanup_artifact import CleanupArtifact, CleanupArtifactStatus
from models.client import Client
from models.associations import EngagementAssignment
from auth.dependencies import get_current_user
from auth.permissions import has_global_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# ── Schemas ──────────────────────────────────────────────────────────

class WidgetCreate(BaseModel):
    name: str = Field(..., max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    widget_type: str = Field(..., max_length=64)
    data_source: str = Field(..., max_length=128)
    size: str = Field("medium", max_length=16)
    category: str = Field("custom", max_length=64)
    icon: Optional[str] = Field(None, max_length=64)
    config: Optional[dict] = None

class WidgetUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    widget_type: Optional[str] = Field(None, max_length=64)
    data_source: Optional[str] = Field(None, max_length=128)
    size: Optional[str] = Field(None, max_length=16)
    category: Optional[str] = Field(None, max_length=64)
    icon: Optional[str] = Field(None, max_length=64)
    config: Optional[dict] = None
    is_active: Optional[bool] = None

class LayoutItem(BaseModel):
    widget_id: str
    x: int = 0
    y: int = 0
    w: int = 1
    h: int = 1

class LayoutUpdate(BaseModel):
    layout: List[LayoutItem]

class QueryFilter(BaseModel):
    column: str = Field(..., max_length=64)
    operator: str = Field("eq", max_length=8)  # eq, ne, gt, lt, gte, lte, like
    value: str = Field(..., max_length=512)

class QueryPreviewRequest(BaseModel):
    table: str = Field(..., max_length=64)
    group_by: str = Field(..., max_length=64)
    aggregation: str = Field("count", max_length=16)  # count, avg, sum, max, min
    value_column: str = Field("id", max_length=64)
    filters: Optional[List[QueryFilter]] = None
    limit: int = 50
    # ── Advanced fields ──
    date_column: Optional[str] = Field(None, max_length=64)       # column to filter/bucket on
    date_range: Optional[str] = Field(None, max_length=16)        # "7d", "30d", "90d", "quarter", "year", "all"
    date_start: Optional[str] = Field(None, max_length=32)        # custom start (ISO date)
    date_end: Optional[str] = Field(None, max_length=32)          # custom end (ISO date)
    time_bucket: Optional[str] = None       # "day", "week", "month" → time-series
    series_by: Optional[str] = None         # column to split into multi-series
    join_tables: Optional[List[str]] = None  # e.g. ["engagements", "clients"]


# ── Query Builder Allowlist ──────────────────────────────────────────

_TABLE_MAP = {
    "findings": Finding,
    "engagements": Engagement,
    "assets": Asset,
    "testcases": TestCase,
    "cleanup_artifacts": CleanupArtifact,
}

_ALLOWED_COLUMNS: dict[str, dict[str, list[str]]] = {
    "findings": {
        "group_by": ["severity", "status", "category", "engagement_id", "created_by"],
        "aggregate": ["id", "cvss_score"],
        "date_columns": ["created_at", "updated_at"],
        "filter_columns": ["severity", "status", "category", "engagement_id", "created_by"],
        "series_by": ["severity", "status", "category"],
    },
    "engagements": {
        "group_by": ["status", "engagement_type", "client_name", "client_id"],
        "aggregate": ["id"],
        "date_columns": ["created_at", "updated_at", "start_date", "end_date"],
        "filter_columns": ["status", "engagement_type", "client_name", "client_id"],
        "series_by": ["status", "engagement_type"],
    },
    "assets": {
        "group_by": ["asset_type", "in_scope", "engagement_id"],
        "aggregate": ["id"],
        "date_columns": ["created_at"],
        "filter_columns": ["asset_type", "in_scope", "engagement_id"],
        "series_by": ["asset_type", "in_scope"],
    },
    "testcases": {
        "group_by": ["category", "engagement_id"],
        "aggregate": ["id", "is_executed", "is_successful"],
        "date_columns": ["created_at"],
        "filter_columns": ["category", "engagement_id"],
        "series_by": ["category"],
    },
    "cleanup_artifacts": {
        "group_by": ["status", "engagement_id"],
        "aggregate": ["id"],
        "date_columns": ["created_at"],
        "filter_columns": ["status", "engagement_id"],
        "series_by": ["status"],
    },
}

# Predefined safe join paths
_JOIN_PATHS = {
    ("findings", "engagements"): lambda: (Engagement, Finding.engagement_id == Engagement.id),
    ("findings", "clients"): lambda: (Client, Engagement.client_id == Client.id),  # requires engagements join first
    ("assets", "engagements"): lambda: (Engagement, Asset.engagement_id == Engagement.id),
    ("testcases", "engagements"): lambda: (Engagement, TestCase.engagement_id == Engagement.id),
    ("cleanup_artifacts", "engagements"): lambda: (Engagement, CleanupArtifact.engagement_id == Engagement.id),
}

# Columns available via JOINs
_JOIN_COLUMNS = {
    "engagement_name": (Engagement, "name"),
    "engagement_status": (Engagement, "status"),
    "engagement_type": (Engagement, "engagement_type"),
    "client_name_joined": (Engagement, "client_name"),
}

_AGG_FUNCS = {
    "count": func.count,
    "avg": func.avg,
    "sum": func.sum,
    "max": func.max,
    "min": func.min,
}

_FILTER_OPS = {
    "eq": lambda col, val: col == val,
    "ne": lambda col, val: col != val,
    "gt": lambda col, val: col > val,
    "lt": lambda col, val: col < val,
    "gte": lambda col, val: col >= val,
    "lte": lambda col, val: col <= val,
    "like": lambda col, val: col.ilike(f"%{val}%"),
}

_DATE_RANGE_MAP = {
    "7d": lambda: datetime.utcnow() - timedelta(days=7),
    "30d": lambda: datetime.utcnow() - timedelta(days=30),
    "90d": lambda: datetime.utcnow() - timedelta(days=90),
    "quarter": lambda: datetime.utcnow() - timedelta(days=91),
    "year": lambda: datetime.utcnow() - timedelta(days=365),
}


# ── Default system widget definitions ────────────────────────────────

SYSTEM_WIDGETS = [
    # Overview stat cards
    {"id": "sys-my-engagements", "name": "My Active Engagements", "widget_type": "stat_card", "data_source": "personal_stats.my_active_engagements", "size": "small", "category": "overview", "icon": "Briefcase", "config": {"variant": "default"}},
    {"id": "sys-my-findings", "name": "My Open Findings", "widget_type": "stat_card", "data_source": "personal_stats.my_open_findings", "size": "small", "category": "overview", "icon": "Bug", "config": {"variant": "danger"}},
    {"id": "sys-pending-tests", "name": "Pending Tests", "widget_type": "stat_card", "data_source": "personal_stats.my_pending_tests", "size": "small", "category": "overview", "icon": "CheckSquare", "config": {"variant": "warning"}},
    {"id": "sys-findings-month", "name": "Findings This Month", "widget_type": "stat_card", "data_source": "personal_stats.my_findings_this_month", "size": "small", "category": "overview", "icon": "Target", "config": {"variant": "success"}},
    {"id": "sys-pending-cleanup", "name": "Pending Cleanup", "widget_type": "stat_card", "data_source": "personal_stats.my_pending_cleanup", "size": "small", "category": "overview", "icon": "Trash2", "config": {"variant": "purple"}},
    {"id": "sys-unread-notifs", "name": "Unread Notifications", "widget_type": "stat_card", "data_source": "personal_stats.my_unread_notifications", "size": "small", "category": "overview", "icon": "AlertTriangle", "config": {"variant": "cyan"}},
    # Charts
    {"id": "sys-severity-breakdown", "name": "Severity Breakdown", "widget_type": "bar_chart", "data_source": "severity_distribution", "size": "medium", "category": "findings", "icon": "BarChart3", "config": {"colors": {"Critical": "#ef4444", "High": "#f97316", "Medium": "#f59e0b", "Low": "#3b82f6", "Info": "#64748b"}}},
    {"id": "sys-finding-status", "name": "Finding Status", "widget_type": "pie_chart", "data_source": "findings_by_status", "size": "medium", "category": "findings", "icon": "CircleDot", "config": {}},
    {"id": "sys-engagement-pipeline", "name": "Engagement Pipeline", "widget_type": "bar_chart", "data_source": "engagement_status", "size": "medium", "category": "engagements", "icon": "Target", "config": {"layout": "vertical"}},
    {"id": "sys-findings-timeline", "name": "Findings Timeline", "widget_type": "area_chart", "data_source": "findings_timeline", "size": "wide", "category": "findings", "icon": "TrendingUp", "config": {}},
    # Lists
    {"id": "sys-my-engagements-list", "name": "My Engagements List", "widget_type": "list", "data_source": "my_engagements", "size": "medium", "category": "overview", "icon": "Briefcase", "config": {"list_type": "engagements"}},
    {"id": "sys-top-findings", "name": "Top Critical Findings", "widget_type": "list", "data_source": "top_findings", "size": "medium", "category": "findings", "icon": "AlertTriangle", "config": {"list_type": "findings"}},
    {"id": "sys-upcoming", "name": "Upcoming Engagements", "widget_type": "list", "data_source": "upcoming_engagements", "size": "medium", "category": "engagements", "icon": "Calendar", "config": {"list_type": "upcoming"}},
    {"id": "sys-team-util", "name": "Team Utilization", "widget_type": "gauge", "data_source": "team_utilization", "size": "small", "category": "operators", "icon": "Users", "config": {}},
    {"id": "sys-activity-feed", "name": "Recent Activity", "widget_type": "list", "data_source": "recent_activity", "size": "large", "category": "overview", "icon": "Activity", "config": {"list_type": "activity"}},
    # Stats page charts available as widgets
    {"id": "sys-engagement-types", "name": "Engagements by Type", "widget_type": "pie_chart", "data_source": "engagement_types", "size": "medium", "category": "engagements", "icon": "Briefcase", "config": {}},
    {"id": "sys-top-contributors", "name": "Top Contributors", "widget_type": "bar_chart", "data_source": "top_contributors", "size": "medium", "category": "operators", "icon": "UserCheck", "config": {}},
    {"id": "sys-cleanup-status", "name": "Cleanup Status", "widget_type": "pie_chart", "data_source": "cleanup_status", "size": "medium", "category": "engagements", "icon": "Trash2", "config": {}},
    {"id": "sys-test-coverage", "name": "Test Case Coverage", "widget_type": "bar_chart", "data_source": "testcase_coverage", "size": "medium", "category": "engagements", "icon": "ClipboardCheck", "config": {}},
    {"id": "sys-findings-category", "name": "Findings by Category", "widget_type": "bar_chart", "data_source": "findings_by_category", "size": "wide", "category": "findings", "icon": "BarChart3", "config": {"layout": "vertical"}},
]

# Default layout — what new users see
DEFAULT_LAYOUT = [
    {"widget_id": "sys-my-engagements", "x": 0, "y": 0, "w": 1, "h": 1},
    {"widget_id": "sys-my-findings", "x": 1, "y": 0, "w": 1, "h": 1},
    {"widget_id": "sys-pending-tests", "x": 2, "y": 0, "w": 1, "h": 1},
    {"widget_id": "sys-findings-month", "x": 3, "y": 0, "w": 1, "h": 1},
    {"widget_id": "sys-pending-cleanup", "x": 4, "y": 0, "w": 1, "h": 1},
    {"widget_id": "sys-unread-notifs", "x": 5, "y": 0, "w": 1, "h": 1},
    {"widget_id": "sys-my-engagements-list", "x": 0, "y": 1, "w": 2, "h": 2},
    {"widget_id": "sys-upcoming", "x": 0, "y": 3, "w": 2, "h": 1},
    {"widget_id": "sys-activity-feed", "x": 2, "y": 1, "w": 4, "h": 3},
]


# ── Endpoints ────────────────────────────────────────────────────────

@router.get("/widgets")
async def list_widgets(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all active widget definitions."""
    result = await db.execute(
        select(DashboardWidget).where(DashboardWidget.is_active == True).order_by(DashboardWidget.category, DashboardWidget.name)
    )
    widgets = result.scalars().all()

    # If no system widgets exist, seed them
    if not any(w.is_system for w in widgets):
        await _seed_system_widgets(db)
        result = await db.execute(
            select(DashboardWidget).where(DashboardWidget.is_active == True).order_by(DashboardWidget.category, DashboardWidget.name)
        )
        widgets = result.scalars().all()

    return [_widget_to_dict(w) for w in widgets]


@router.post("/widgets", status_code=201)
async def create_widget(
    data: WidgetCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a custom widget definition (admin only)."""
    if not await has_global_permission(current_user, Permission.MANAGE_DASHBOARD_WIDGETS, db):
        raise HTTPException(status_code=403, detail="Permission denied")
    widget = DashboardWidget(
        name=data.name,
        description=data.description,
        widget_type=data.widget_type,
        data_source=data.data_source,
        size=data.size,
        category=data.category,
        icon=data.icon,
        config=data.config or {},
        is_system=False,
        created_by=current_user.id,
    )
    db.add(widget)
    await db.commit()
    await db.refresh(widget)
    return _widget_to_dict(widget)


@router.put("/widgets/{widget_id}")
async def update_widget(
    widget_id: str,
    data: WidgetUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a widget definition (admin only)."""
    if not await has_global_permission(current_user, Permission.MANAGE_DASHBOARD_WIDGETS, db):
        raise HTTPException(status_code=403, detail="Permission denied")
    result = await db.execute(select(DashboardWidget).where(DashboardWidget.id == widget_id))
    widget = result.scalar_one_or_none()
    if not widget:
        raise HTTPException(status_code=404, detail="Widget not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(widget, key, value)

    await db.commit()
    await db.refresh(widget)
    return _widget_to_dict(widget)


@router.delete("/widgets/{widget_id}")
async def delete_widget(
    widget_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a non-system widget (admin only)."""
    if not await has_global_permission(current_user, Permission.MANAGE_DASHBOARD_WIDGETS, db):
        raise HTTPException(status_code=403, detail="Permission denied")
    result = await db.execute(select(DashboardWidget).where(DashboardWidget.id == widget_id))
    widget = result.scalar_one_or_none()
    if not widget:
        raise HTTPException(status_code=404, detail="Widget not found")
    if widget.is_system:
        raise HTTPException(status_code=403, detail="Cannot delete system widgets")

    await db.delete(widget)
    await db.commit()
    return {"status": "deleted"}


# ── User layout endpoints ────────────────────────────────────────────

@router.get("/layout")
async def get_layout(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user's dashboard layout. Returns default if none saved."""
    # Refresh user to get latest
    await db.refresh(current_user)
    layout = current_user.dashboard_layout
    if layout is None:
        layout = DEFAULT_LAYOUT
    return {"layout": layout, "is_default": current_user.dashboard_layout is None}


@router.put("/layout")
async def save_layout(
    data: LayoutUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save user's dashboard layout. Any authenticated user can customize their own view."""
    layout_dicts = [item.model_dump() for item in data.layout]
    current_user.dashboard_layout = layout_dicts
    await db.commit()
    return {"status": "saved", "layout": layout_dicts}


@router.post("/layout/reset")
async def reset_layout(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reset user's dashboard layout to default."""
    current_user.dashboard_layout = None
    await db.commit()
    return {"status": "reset", "layout": DEFAULT_LAYOUT}


# ── Custom Query Builder Endpoints ───────────────────────────────────


def _resolve_date_filter(req: QueryPreviewRequest, model):
    """Build date-range WHERE clause from the request."""
    if not req.date_column or not req.date_range:
        return None
    allowed = _ALLOWED_COLUMNS.get(req.table, {})
    if req.date_column not in allowed.get("date_columns", []):
        raise HTTPException(400, f"Cannot use '{req.date_column}' as date column. Allowed: {allowed.get('date_columns', [])}")
    date_col = getattr(model, req.date_column)

    if req.date_range == "custom":
        conditions = []
        if req.date_start:
            conditions.append(date_col >= datetime.fromisoformat(req.date_start))
        if req.date_end:
            conditions.append(date_col <= datetime.fromisoformat(req.date_end))
        return and_(*conditions) if conditions else None

    if req.date_range == "all":
        return None

    range_fn = _DATE_RANGE_MAP.get(req.date_range)
    if not range_fn:
        raise HTTPException(400, f"Unknown date_range '{req.date_range}'. Allowed: 7d, 30d, 90d, quarter, year, all, custom")
    return date_col >= range_fn()


def _apply_joins(query, req: QueryPreviewRequest):
    """Apply predefined JOINs to the query."""
    if not req.join_tables:
        return query
    joined = set()
    for jtable in req.join_tables:
        key = (req.table, jtable)
        if key not in _JOIN_PATHS:
            raise HTTPException(400, f"No join path from '{req.table}' to '{jtable}'")
        # If joining clients, ensure engagements is joined first
        if jtable == "clients" and "engagements" not in joined:
            eng_key = (req.table, "engagements")
            if eng_key in _JOIN_PATHS:
                target_model, condition = _JOIN_PATHS[eng_key]()
                query = query.join(target_model, condition, isouter=True)
                joined.add("engagements")
        target_model, condition = _JOIN_PATHS[key]()
        if jtable not in joined:
            query = query.join(target_model, condition, isouter=True)
            joined.add(jtable)
    return query


def _build_query(req: QueryPreviewRequest):
    """Build a safe SQLAlchemy query from a structured definition. No raw SQL.
    Supports: standard group-by, time-series bucketing, and multi-series."""
    if req.table not in _TABLE_MAP:
        raise HTTPException(400, f"Table '{req.table}' is not allowed. Allowed: {list(_TABLE_MAP.keys())}")
    model = _TABLE_MAP[req.table]
    allowed = _ALLOWED_COLUMNS[req.table]

    if req.group_by not in allowed["group_by"]:
        raise HTTPException(400, f"Cannot group by '{req.group_by}'. Allowed: {allowed['group_by']}")
    if req.value_column not in allowed["aggregate"]:
        raise HTTPException(400, f"Cannot aggregate '{req.value_column}'. Allowed: {allowed['aggregate']}")
    if req.aggregation not in _AGG_FUNCS:
        raise HTTPException(400, f"Unknown aggregation '{req.aggregation}'. Allowed: {list(_AGG_FUNCS.keys())}")

    value_col = getattr(model, req.value_column)
    agg_fn = _AGG_FUNCS[req.aggregation]

    # Validate series_by
    if req.series_by:
        if req.series_by not in allowed.get("series_by", []):
            raise HTTPException(400, f"Cannot split series by '{req.series_by}'. Allowed: {allowed.get('series_by', [])}")

    # ── Time-series mode ──
    if req.time_bucket and req.date_column:
        if req.time_bucket not in ("day", "week", "month"):
            raise HTTPException(400, "time_bucket must be 'day', 'week', or 'month'")
        if req.date_column not in allowed.get("date_columns", []):
            raise HTTPException(400, f"Cannot bucket by '{req.date_column}'")

        date_col = getattr(model, req.date_column)
        # Use func.date_trunc for PostgreSQL
        bucket = func.date_trunc(req.time_bucket, date_col).label("date")

        if req.series_by:
            # Multi-series time-series: returns {date, series_val, value}
            series_col = getattr(model, req.series_by)
            query = select(
                bucket,
                series_col.label("series"),
                agg_fn(value_col).label("value"),
            ).group_by(bucket, series_col).order_by(bucket)
        else:
            query = select(
                bucket,
                agg_fn(value_col).label("value"),
            ).group_by(bucket).order_by(bucket)
    else:
        # ── Standard group-by mode ──
        group_col = getattr(model, req.group_by)
        query = select(
            group_col.label("label"),
            agg_fn(value_col).label("value"),
        ).group_by(group_col)
        query = query.order_by(agg_fn(value_col).desc())

    # Apply JOINs
    query = _apply_joins(query, req)

    # Apply date-range filter
    date_filter = _resolve_date_filter(req, model)
    if date_filter is not None:
        query = query.where(date_filter)

    # Apply custom filters
    if req.filters:
        conditions = []
        filter_allowed = allowed.get("filter_columns", allowed["group_by"])
        for f in req.filters:
            if f.column not in filter_allowed and f.column not in allowed["aggregate"]:
                raise HTTPException(400, f"Cannot filter by '{f.column}'. Allowed: {filter_allowed}")
            col = getattr(model, f.column)
            op = _FILTER_OPS.get(f.operator)
            if not op:
                raise HTTPException(400, f"Unknown filter operator '{f.operator}'")
            conditions.append(op(col, f.value))
        query = query.where(and_(*conditions))

    # Limit
    limit = min(max(1, req.limit), 500)
    query = query.limit(limit)
    return query


def _format_time_series_result(rows, has_series: bool):
    """Format time-series query results into chart-ready data."""
    if not has_series:
        return {
            "data": [
                {"date": r.date.isoformat() if r.date else None, "value": float(r.value) if r.value else 0}
                for r in rows
            ],
            "mode": "time_series",
        }

    # Multi-series: pivot rows into {date: ..., SeriesA: val, SeriesB: val}
    date_map = {}
    all_series = set()
    for r in rows:
        date_str = r.date.isoformat() if r.date else None
        series_val = str(r.series) if r.series else "(none)"
        all_series.add(series_val)
        if date_str not in date_map:
            date_map[date_str] = {"date": date_str}
        date_map[date_str][series_val] = float(r.value) if r.value else 0

    # Fill missing series with 0
    for entry in date_map.values():
        for s in all_series:
            if s not in entry:
                entry[s] = 0

    return {
        "data": sorted(date_map.values(), key=lambda x: x["date"] or ""),
        "series": sorted(all_series),
        "mode": "multi_series",
    }


@router.post("/widgets/query-preview")
async def query_preview(
    req: QueryPreviewRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Preview results of a custom query definition. Admin only."""
    if not await has_global_permission(current_user, Permission.MANAGE_DASHBOARD_WIDGETS, db):
        raise HTTPException(status_code=403, detail="Permission denied")

    query = _build_query(req)
    result = await db.execute(query)
    rows = result.all()

    # Time-series mode
    if req.time_bucket and req.date_column:
        return _format_time_series_result(rows, has_series=bool(req.series_by))

    # Standard mode
    return {
        "data": [{"label": str(r.label) if r.label else "(none)", "value": float(r.value) if r.value else 0} for r in rows],
        "mode": "standard",
    }


@router.get("/widgets/{widget_id}/data")
async def get_widget_data(
    widget_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get data for a custom-query widget."""
    result = await db.execute(select(DashboardWidget).where(DashboardWidget.id == widget_id))
    widget = result.scalar_one_or_none()
    if not widget:
        raise HTTPException(404, "Widget not found")
    if widget.data_source != "custom_query":
        raise HTTPException(400, "Widget does not use custom_query data source")

    query_config = widget.config.get("query")
    if not query_config:
        return {"data": []}

    req = QueryPreviewRequest(**query_config)
    query = _build_query(req)
    # GHSA-f9x8-qmr3-jrv9: scope non-admins to engagements they're assigned to.
    if current_user.role not in (UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD):
        eng_sq = select(EngagementAssignment.engagement_id).where(
            EngagementAssignment.user_id == current_user.id
        )
        model = _TABLE_MAP[req.table]
        if req.table == "engagements":
            query = query.where(model.id.in_(eng_sq))
        elif hasattr(model, "engagement_id"):
            query = query.where(model.engagement_id.in_(eng_sq))
    result = await db.execute(query)
    rows = result.all()

    # Time-series mode
    if req.time_bucket and req.date_column:
        return _format_time_series_result(rows, has_series=bool(req.series_by))

    return {
        "data": [{"label": str(r.label) if r.label else "(none)", "value": float(r.value) if r.value else 0} for r in rows],
        "mode": "standard",
    }


@router.get("/widgets/query-schema")
async def get_query_schema(
    current_user: User = Depends(get_current_user),
):
    """Return the query builder schema — available tables, columns, join paths, etc.
    Used by the frontend to build the visual query builder dynamically."""
    schema = {}
    for table_name, columns in _ALLOWED_COLUMNS.items():
        schema[table_name] = {
            "group_by": columns["group_by"],
            "aggregate": columns["aggregate"],
            "date_columns": columns.get("date_columns", []),
            "filter_columns": columns.get("filter_columns", columns["group_by"]),
            "series_by": columns.get("series_by", []),
            "joins": [jt for (ft, jt) in _JOIN_PATHS.keys() if ft == table_name],
        }
    return {
        "tables": list(_TABLE_MAP.keys()),
        "schema": schema,
        "aggregations": list(_AGG_FUNCS.keys()),
        "filter_operators": list(_FILTER_OPS.keys()),
        "date_ranges": ["7d", "30d", "90d", "quarter", "year", "all", "custom"],
        "time_buckets": ["day", "week", "month"],
    }


@router.get("/widgets/computed-metrics")
async def get_computed_metrics(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return pre-computed advanced metrics that can't be expressed as simple GROUP BY."""

    # 1. Average findings per engagement
    result = await db.execute(
        select(func.count(Finding.id).label("total_findings"), func.count(func.distinct(Finding.engagement_id)).label("total_engagements"))
    )
    row = result.one()
    findings_per_engagement = round(row.total_findings / max(row.total_engagements, 1), 1)

    # 2. Engagement completion rate
    result = await db.execute(
        select(
            func.count(case((Engagement.status == "COMPLETED", 1))).label("completed"),
            func.count(Engagement.id).label("total"),
        )
    )
    row = result.one()
    completion_rate = round((row.completed / max(row.total, 1)) * 100, 1)

    # 3. Critical/High finding ratio
    result = await db.execute(
        select(
            func.count(case((Finding.severity.in_(["CRITICAL", "HIGH"]), 1))).label("critical_high"),
            func.count(Finding.id).label("total"),
        )
    )
    row = result.one()
    critical_high_ratio = round((row.critical_high / max(row.total, 1)) * 100, 1)

    # 4. Average CVSS score
    result = await db.execute(
        select(func.avg(Finding.cvss_score).label("avg_cvss"))
        .where(Finding.cvss_score.isnot(None))
    )
    avg_cvss = round(float(result.scalar() or 0), 1)

    # 5. Assets per engagement
    result = await db.execute(
        select(func.count(Asset.id).label("total_assets"), func.count(func.distinct(Asset.engagement_id)).label("total_engagements"))
    )
    row = result.one()
    assets_per_engagement = round(row.total_assets / max(row.total_engagements, 1), 1)

    # 6. Test case pass rate
    result = await db.execute(
        select(
            func.count(case((TestCase.is_successful == True, 1))).label("passed"),
            func.count(case((TestCase.is_executed == True, 1))).label("executed"),
        )
    )
    row = result.one()
    pass_rate = round((row.passed / max(row.executed, 1)) * 100, 1)

    return {
        "metrics": [
            {"key": "findings_per_engagement", "label": "Avg Findings / Engagement", "value": findings_per_engagement, "icon": "Target", "format": "number"},
            {"key": "completion_rate", "label": "Engagement Completion Rate", "value": completion_rate, "icon": "CheckSquare", "format": "percent"},
            {"key": "critical_high_ratio", "label": "Critical/High Finding %", "value": critical_high_ratio, "icon": "AlertTriangle", "format": "percent"},
            {"key": "avg_cvss", "label": "Average CVSS Score", "value": avg_cvss, "icon": "Shield", "format": "score"},
            {"key": "assets_per_engagement", "label": "Avg Assets / Engagement", "value": assets_per_engagement, "icon": "Server", "format": "number"},
            {"key": "test_pass_rate", "label": "Test Case Pass Rate", "value": pass_rate, "icon": "ClipboardCheck", "format": "percent"},
        ]
    }


# ── Helpers ──────────────────────────────────────────────────────────

def _widget_to_dict(w: DashboardWidget) -> dict:
    return {
        "id": w.id,
        "name": w.name,
        "description": w.description,
        "widget_type": w.widget_type,
        "data_source": w.data_source,
        "size": w.size,
        "category": w.category,
        "icon": w.icon,
        "config": w.config or {},
        "is_system": w.is_system,
        "is_active": w.is_active,
    }


async def _seed_system_widgets(db: AsyncSession):
    """Seed built-in system widgets if they don't exist."""
    for w_data in SYSTEM_WIDGETS:
        existing = await db.execute(
            select(DashboardWidget).where(DashboardWidget.id == w_data["id"])
        )
        if existing.scalar_one_or_none() is None:
            widget = DashboardWidget(
                id=w_data["id"],
                name=w_data["name"],
                widget_type=w_data["widget_type"],
                data_source=w_data["data_source"],
                size=w_data["size"],
                category=w_data["category"],
                icon=w_data.get("icon"),
                config=w_data.get("config", {}),
                is_system=True,
                is_active=True,
            )
            db.add(widget)
    await db.commit()
