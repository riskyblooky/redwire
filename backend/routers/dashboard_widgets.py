"""
Dashboard Widgets router — CRUD for widget definitions + user layout management.
Includes advanced custom query builder with JOINs, date-range filtering,
time-series bucketing, and multi-series support.
"""

import logging
from typing import Optional, List
from datetime import datetime, timedelta
from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException, status, Query
from schemas._field_limits import MAX_LIST_LIMIT
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
from models.note import Note
from models.evidence import Evidence
from models.vault import VaultItem
from models.automation import AutomationRule
from models.notification import Notification
from models.discussion import Thread, Comment, ActivityLog
from models.intel_item import IntelItem
from models.intel_feed import IntelFeed
from models.infra_item import InfraItem
from models.spray import SprayCampaign, SprayResult
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
    operator: str = Field("eq", max_length=16)  # covers up to is_not_null
    value: str = Field("", max_length=512)  # blank when operator is presence-only

class MultiQueryPreviewRequest(BaseModel):
    """Multiple parallel sub-queries used by compositional widgets
    (ratio / percentage / delta / overlay). Each entry gets executed
    independently; the frontend combines the results per widget type.
    """
    queries: List["QueryPreviewRequest"] = Field(..., min_length=1, max_length=6)


class QueryPreviewRequest(BaseModel):
    table: str = Field(..., max_length=64)
    # ``group_by`` accepts either a single column (back-compat) or a list
    # for 2D pivots ("severity × status"). Every column must be in the
    # table's group_by allowlist. Single-string form is normalised into
    # a 1-element list inside _build_query.
    group_by: str | List[str] = Field(...)
    aggregation: str = Field("count", max_length=16)
    value_column: str = Field("id", max_length=64)
    filters: Optional[List[QueryFilter]] = None
    limit: int = Query(50, ge=1, le=MAX_LIST_LIMIT)
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
    # Original core five
    "findings": Finding,
    "engagements": Engagement,
    "assets": Asset,
    "testcases": TestCase,
    "cleanup_artifacts": CleanupArtifact,
    # Phase 1 expansion — 15 more tables covering people, records, ops,
    # collaboration, and intelligence subsystems.
    "users": User,
    "clients": Client,
    "notes": Note,
    "evidence": Evidence,
    "vault_items": VaultItem,               # sensitive — see _SENSITIVE_TABLES
    "automation_rules": AutomationRule,
    "notifications": Notification,           # sensitive — see _SENSITIVE_TABLES
    "activity_logs": ActivityLog,
    "threads": Thread,
    "comments": Comment,
    "intel_items": IntelItem,
    "intel_feeds": IntelFeed,
    "infra_items": InfraItem,
    "spray_campaigns": SprayCampaign,
    "spray_results": SprayResult,
}


# Tables that leak per-user or credential-adjacent data and MUST NOT be
# queryable by anyone below MANAGE_DASHBOARD_WIDGETS + admin/team-lead:
#   - vault_items: names/types can hint at credentials in use.
#   - notifications: every user's inbox → easy per-user surveillance.
# The runtime gate lives in _assert_query_access.
_SENSITIVE_TABLES = {"vault_items", "notifications"}


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
    # ── Team & org ──────────────────────────────────────────────────
    "users": {
        "group_by": ["role", "is_active", "auth_provider", "theme_preference"],
        "aggregate": ["id"],
        "date_columns": ["created_at", "last_login", "last_active"],
        "filter_columns": ["role", "is_active", "auth_provider"],
        "series_by": ["role", "auth_provider"],
    },
    "clients": {
        "group_by": ["client_type_id", "parent_id"],
        "aggregate": ["id"],
        "date_columns": ["created_at", "updated_at"],
        "filter_columns": ["client_type_id", "parent_id"],
        "series_by": ["client_type_id"],
    },
    # ── Content & knowledge ────────────────────────────────────────
    "notes": {
        "group_by": ["engagement_id", "created_by", "parent_id"],
        "aggregate": ["id"],
        "date_columns": ["created_at", "updated_at"],
        "filter_columns": ["engagement_id", "created_by"],
        "series_by": ["created_by"],
    },
    "evidence": {
        "group_by": ["mime_type", "engagement_id", "finding_id", "testcase_id", "include_in_report"],
        "aggregate": ["id", "file_size"],
        "date_columns": ["created_at"],
        "filter_columns": ["mime_type", "engagement_id", "finding_id", "include_in_report"],
        "series_by": ["mime_type"],
    },
    "vault_items": {
        "group_by": ["item_type", "engagement_id"],
        "aggregate": ["id"],
        "date_columns": ["created_at", "updated_at"],
        "filter_columns": ["item_type", "engagement_id"],
        "series_by": ["item_type"],
    },
    # ── Automation & delivery ──────────────────────────────────────
    "automation_rules": {
        "group_by": ["trigger_type", "is_enabled", "owner_user_id", "engagement_id"],
        "aggregate": ["id", "trigger_count"],
        "date_columns": ["created_at", "updated_at", "last_triggered_at"],
        "filter_columns": ["trigger_type", "is_enabled", "owner_user_id", "engagement_id"],
        "series_by": ["trigger_type", "is_enabled"],
    },
    "notifications": {
        "group_by": ["event_type", "is_read", "user_id", "actor_id", "engagement_id"],
        "aggregate": ["id"],
        "date_columns": ["created_at"],
        "filter_columns": ["event_type", "is_read", "user_id", "engagement_id"],
        "series_by": ["event_type", "is_read"],
    },
    "activity_logs": {
        "group_by": ["action", "resource_type", "user_id", "engagement_id"],
        "aggregate": ["id"],
        "date_columns": ["created_at"],
        "filter_columns": ["action", "resource_type", "user_id", "engagement_id"],
        "series_by": ["action", "resource_type"],
    },
    # ── Collaboration ──────────────────────────────────────────────
    "threads": {
        "group_by": ["resource_type", "is_resolved", "created_by", "engagement_id"],
        "aggregate": ["id"],
        "date_columns": ["created_at"],
        "filter_columns": ["resource_type", "is_resolved", "created_by", "engagement_id"],
        "series_by": ["resource_type", "is_resolved"],
    },
    "comments": {
        "group_by": ["thread_id", "created_by", "is_resolved", "is_resolvable"],
        "aggregate": ["id"],
        "date_columns": ["created_at", "resolved_at"],
        "filter_columns": ["thread_id", "created_by", "is_resolved"],
        "series_by": ["is_resolved"],
    },
    # ── Intelligence ───────────────────────────────────────────────
    "intel_items": {
        "group_by": ["item_type", "severity", "source", "feed_id"],
        "aggregate": ["id"],
        "date_columns": ["created_at", "updated_at", "published_at"],
        "filter_columns": ["item_type", "severity", "source", "feed_id", "cve_id"],
        "series_by": ["item_type", "severity"],
    },
    "intel_feeds": {
        "group_by": ["feed_type", "enabled"],
        "aggregate": ["id"],
        "date_columns": ["created_at", "last_fetched_at"],
        "filter_columns": ["feed_type", "enabled"],
        "series_by": ["feed_type"],
    },
    # ── Infrastructure ─────────────────────────────────────────────
    "infra_items": {
        "group_by": ["infra_type", "status", "provider", "region"],
        "aggregate": ["id"],
        "date_columns": ["created_at"],
        "filter_columns": ["infra_type", "status", "provider", "region"],
        "series_by": ["infra_type", "status"],
    },
    # ── Spray ops ──────────────────────────────────────────────────
    "spray_campaigns": {
        "group_by": ["protocol", "status", "engagement_id", "target_hostname", "domain"],
        "aggregate": ["id", "total_attempts", "successful", "locked_out", "failed"],
        "date_columns": ["created_at", "updated_at"],
        "filter_columns": ["protocol", "status", "engagement_id", "domain"],
        "series_by": ["protocol", "status"],
    },
    "spray_results": {
        "group_by": ["result", "is_admin", "campaign_id", "domain"],
        "aggregate": ["id"],
        "date_columns": [],   # no created_at on SprayResult
        "filter_columns": ["result", "is_admin", "campaign_id", "domain"],
        "series_by": ["result"],
    },
}

# ── Join graph ──────────────────────────────────────────────────────
#
# Each entry declares an edge (from → to) plus the SQLAlchemy join
# condition. When the caller asks for join_tables=[X, Y, Z], the query
# builder walks each requested edge in the order given, ensuring
# dependencies are added first via ``_via`` chains. Extending is a
# matter of appending one row per new join — the walker figures out
# the rest.
_JOIN_PATHS = {
    # Findings
    ("findings", "engagements"): lambda: (Engagement, Finding.engagement_id == Engagement.id),
    ("findings", "clients"): lambda: (Client, Engagement.client_id == Client.id),
    # Assets / testcases / cleanup
    ("assets", "engagements"): lambda: (Engagement, Asset.engagement_id == Engagement.id),
    ("assets", "clients"): lambda: (Client, Engagement.client_id == Client.id),
    ("testcases", "engagements"): lambda: (Engagement, TestCase.engagement_id == Engagement.id),
    ("testcases", "clients"): lambda: (Client, Engagement.client_id == Client.id),
    ("cleanup_artifacts", "engagements"): lambda: (Engagement, CleanupArtifact.engagement_id == Engagement.id),
    ("cleanup_artifacts", "clients"): lambda: (Client, Engagement.client_id == Client.id),
    # Content
    ("notes", "engagements"): lambda: (Engagement, Note.engagement_id == Engagement.id),
    ("notes", "users"): lambda: (User, Note.created_by == User.id),
    ("evidence", "engagements"): lambda: (Engagement, Evidence.engagement_id == Engagement.id),
    ("evidence", "findings"): lambda: (Finding, Evidence.finding_id == Finding.id),
    ("evidence", "testcases"): lambda: (TestCase, Evidence.testcase_id == TestCase.id),
    ("vault_items", "engagements"): lambda: (Engagement, VaultItem.engagement_id == Engagement.id),
    # Automation / notifications / activity
    ("automation_rules", "users"): lambda: (User, AutomationRule.created_by == User.id),
    ("automation_rules", "engagements"): lambda: (Engagement, AutomationRule.engagement_id == Engagement.id),
    ("notifications", "users"): lambda: (User, Notification.user_id == User.id),
    ("notifications", "engagements"): lambda: (Engagement, Notification.engagement_id == Engagement.id),
    ("activity_logs", "users"): lambda: (User, ActivityLog.user_id == User.id),
    ("activity_logs", "engagements"): lambda: (Engagement, ActivityLog.engagement_id == Engagement.id),
    # Collaboration
    ("threads", "engagements"): lambda: (Engagement, Thread.engagement_id == Engagement.id),
    ("threads", "users"): lambda: (User, Thread.created_by == User.id),
    ("comments", "threads"): lambda: (Thread, Comment.thread_id == Thread.id),
    ("comments", "users"): lambda: (User, Comment.created_by == User.id),
    ("comments", "engagements"): lambda: (Engagement, Thread.engagement_id == Engagement.id),
    # Intel
    ("intel_items", "intel_feeds"): lambda: (IntelFeed, IntelItem.feed_id == IntelFeed.id),
    ("intel_items", "users"): lambda: (User, IntelItem.created_by == User.id),
    ("intel_feeds", "users"): lambda: (User, IntelFeed.created_by == User.id),
    # Spray
    ("spray_campaigns", "engagements"): lambda: (Engagement, SprayCampaign.engagement_id == Engagement.id),
    ("spray_campaigns", "clients"): lambda: (Client, Engagement.client_id == Client.id),
    ("spray_results", "spray_campaigns"): lambda: (SprayCampaign, SprayResult.campaign_id == SprayCampaign.id),
    ("spray_results", "engagements"): lambda: (Engagement, SprayCampaign.engagement_id == Engagement.id),
    # Clients
    ("engagements", "clients"): lambda: (Client, Engagement.client_id == Client.id),
}

# When a requested join depends on an intermediate join being present,
# declare it here. Keys are (from_table, to_table), values are the list
# of prerequisite intermediate tables that must be joined first.
_JOIN_PREREQS: dict[tuple[str, str], list[str]] = {
    ("findings", "clients"): ["engagements"],
    ("assets", "clients"): ["engagements"],
    ("testcases", "clients"): ["engagements"],
    ("cleanup_artifacts", "clients"): ["engagements"],
    ("spray_campaigns", "clients"): ["engagements"],
    ("spray_results", "spray_campaigns"): [],
    ("spray_results", "engagements"): ["spray_campaigns"],
    ("comments", "engagements"): ["threads"],
}

# Columns available via JOINs
_JOIN_COLUMNS = {
    "engagement_name": (Engagement, "name"),
    "engagement_status": (Engagement, "status"),
    "engagement_type": (Engagement, "engagement_type"),
    "client_name_joined": (Engagement, "client_name"),
}

_AGG_FUNCS = {
    "count": lambda col: func.count(col),
    "avg": lambda col: func.avg(col),
    "sum": lambda col: func.sum(col),
    "max": lambda col: func.max(col),
    "min": lambda col: func.min(col),
    # Distinct-count: "how many unique values" — heavier than count() so
    # cap use to allowlisted columns just like the base aggregations.
    "count_distinct": lambda col: func.count(func.distinct(col)),
    # Percentiles use PG's ordered-set aggregate. Fixed common breakpoints
    # instead of an arbitrary percentile param so the API stays declarative
    # and the frontend picker is enumerable.
    "median": lambda col: func.percentile_cont(0.5).within_group(col.asc()),
    "p95": lambda col: func.percentile_cont(0.95).within_group(col.asc()),
    "p99": lambda col: func.percentile_cont(0.99).within_group(col.asc()),
}


def _parse_csv(v: str) -> list[str]:
    """Split a filter value on commas and trim; blanks dropped."""
    return [s.strip() for s in v.split(",") if s.strip()]


def _coerce(col, s: str):
    """Coerce a string filter value to the column's Python type when the
    target is numeric or boolean. Strings pass through unchanged so
    existing enum/status filters keep working. PG can't implicitly
    convert varchar → double precision, so we do it here."""
    try:
        py_type = getattr(getattr(col, "type", None), "python_type", None)
    except Exception:
        return s
    if py_type is None:
        return s
    if py_type is int:
        try:
            return int(s)
        except ValueError:
            return s
    if py_type is float:
        try:
            return float(s)
        except ValueError:
            return s
    if py_type is bool:
        return s.strip().lower() in ("true", "t", "1", "yes", "y")
    return s


_FILTER_OPS = {
    "eq":         lambda col, val: col == _coerce(col, val),
    "ne":         lambda col, val: col != _coerce(col, val),
    "gt":         lambda col, val: col > _coerce(col, val),
    "lt":         lambda col, val: col < _coerce(col, val),
    "gte":        lambda col, val: col >= _coerce(col, val),
    "lte":        lambda col, val: col <= _coerce(col, val),
    "like":       lambda col, val: col.ilike(f"%{val}%"),
    "not_like":   lambda col, val: ~col.ilike(f"%{val}%"),
    # Multi-value: value is a comma-separated list ("critical,high,medium").
    "in":         lambda col, val: col.in_([_coerce(col, x) for x in _parse_csv(val)]),
    "not_in":     lambda col, val: col.notin_([_coerce(col, x) for x in _parse_csv(val)]),
    # Presence checks — value is ignored on the wire.
    "is_null":     lambda col, _val: col.is_(None),
    "is_not_null": lambda col, _val: col.isnot(None),
    # Range: value is "min,max"; both sides inclusive to match date-range
    # semantics elsewhere in the codebase.
    "between": lambda col, val: (
        col.between(_coerce(col, _parse_csv(val)[0]), _coerce(col, _parse_csv(val)[1]))
        if len(_parse_csv(val)) == 2
        else col == None    # noqa: E711 — malformed input matches nothing
    ),
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


def _assert_query_access(req: "QueryPreviewRequest", current_user: User) -> None:
    """Gate access to sensitive tables. Anyone with MANAGE_DASHBOARD_WIDGETS
    can already reach the query endpoints, but for the vault/notifications
    class we tighten further to admin / read-only-admin / team-lead — a
    normal operator with widget-customize permission should not be able
    to enumerate credential names or per-user inbox contents.
    """
    all_tables = {req.table}
    if req.join_tables:
        all_tables.update(req.join_tables)
    if all_tables & _SENSITIVE_TABLES:
        if current_user.role not in (UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD):
            raise HTTPException(
                status_code=403,
                detail=f"Tables {sorted(_SENSITIVE_TABLES & all_tables)} require admin or team-lead role",
            )


def _apply_joins(query, req: "QueryPreviewRequest"):
    """Walk the requested join list, adding each edge in order and
    inserting any declared prerequisites first. Duplicate joins are
    silently coalesced so a caller asking for the same table twice
    doesn't blow up the query planner."""
    if not req.join_tables:
        return query
    joined: set[str] = set()

    def _add_edge(jtable: str) -> object:
        """Recursive: add prereqs first, then the edge itself. Returns the
        (possibly mutated) query. Uses a nonlocal ``query`` so recursion
        can chain updates without the caller threading it through."""
        nonlocal query
        if jtable in joined:
            return query
        key = (req.table, jtable)
        if key not in _JOIN_PATHS:
            raise HTTPException(400, f"No join path from '{req.table}' to '{jtable}'")
        for prereq in _JOIN_PREREQS.get(key, []):
            _add_edge(prereq)
        target_model, condition = _JOIN_PATHS[key]()
        query = query.join(target_model, condition, isouter=True)
        joined.add(jtable)
        return query

    for jtable in req.join_tables:
        _add_edge(jtable)
    return query


def _build_query(req: QueryPreviewRequest):
    """Build a safe SQLAlchemy query from a structured definition. No raw SQL.
    Supports: standard group-by, time-series bucketing, and multi-series."""
    if req.table not in _TABLE_MAP:
        raise HTTPException(400, f"Table '{req.table}' is not allowed. Allowed: {list(_TABLE_MAP.keys())}")
    model = _TABLE_MAP[req.table]
    allowed = _ALLOWED_COLUMNS[req.table]

    # Normalise group_by to a list. Single-string form still works —
    # callers built against the old shape don't need to change. Every
    # column must be in the table's group_by allowlist.
    group_by_cols = req.group_by if isinstance(req.group_by, list) else [req.group_by]
    if not group_by_cols:
        raise HTTPException(400, "group_by requires at least one column")
    if len(group_by_cols) > 3:
        raise HTTPException(400, "group_by supports up to 3 columns")
    for col_name in group_by_cols:
        if col_name not in allowed["group_by"]:
            raise HTTPException(400, f"Cannot group by '{col_name}'. Allowed: {allowed['group_by']}")

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
        bucket = func.date_trunc(req.time_bucket, date_col).label("date")

        if req.series_by:
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
        # Multi-column: emit a labelN column per dim, group by all of them.
        # Frontend renders as a compound key ("Critical / Open") for
        # single-bucket viz, or as a 2D heatmap when there are exactly 2.
        cols = [getattr(model, c) for c in group_by_cols]
        selects: list = []
        for i, col in enumerate(cols):
            selects.append(col.label(f"label{i}" if i > 0 else "label"))
        selects.append(agg_fn(value_col).label("value"))
        query = select(*selects).group_by(*cols).order_by(agg_fn(value_col).desc())

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


def _format_standard_result(rows, group_by_cols: list[str]) -> dict:
    """Format standard-mode rows. Single-column groups → {label, value}
    (unchanged shape, back-compat). Multi-column → the primary label plus
    ``labels`` array holding every dim so the frontend can render a
    heatmap / 2-key list without a second round trip."""
    is_multi = len(group_by_cols) > 1
    data = []
    for r in rows:
        raw_labels: list[str] = []
        primary = getattr(r, "label", None)
        raw_labels.append(str(primary) if primary is not None else "(none)")
        for i in range(1, len(group_by_cols)):
            v = getattr(r, f"label{i}", None)
            raw_labels.append(str(v) if v is not None else "(none)")
        entry: dict = {
            "label": raw_labels[0] if not is_multi else " / ".join(raw_labels),
            "value": float(r.value) if r.value else 0,
        }
        if is_multi:
            entry["labels"] = raw_labels
            entry["dims"] = dict(zip(group_by_cols, raw_labels))
        data.append(entry)
    return {"data": data, "mode": "standard", "group_by": group_by_cols}


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


async def _run_single_query(
    req: QueryPreviewRequest,
    current_user: User,
    db: AsyncSession,
    *,
    scope_to_user: bool = False,
) -> dict:
    """Execute one QueryPreviewRequest and return its formatted result.
    Shared by the single-query preview, the multi-query preview, and
    the widget-data endpoint. When ``scope_to_user`` is True, non-admin
    callers are constrained to their own engagement assignments.
    """
    _assert_query_access(req, current_user)
    query = _build_query(req)
    if scope_to_user and current_user.role not in (
        UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD,
    ):
        eng_sq = select(EngagementAssignment.engagement_id).where(
            EngagementAssignment.user_id == current_user.id
        )
        model = _TABLE_MAP[req.table]
        if req.table == "engagements":
            query = query.where(model.id.in_(eng_sq))
        elif hasattr(model, "engagement_id"):
            query = query.where(model.engagement_id.in_(eng_sq))
    rows = (await db.execute(query)).all()
    if req.time_bucket and req.date_column:
        return _format_time_series_result(rows, has_series=bool(req.series_by))
    return _format_standard_result(
        rows,
        req.group_by if isinstance(req.group_by, list) else [req.group_by],
    )


@router.post("/widgets/query-preview")
async def query_preview(
    req: QueryPreviewRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Preview results of a custom query definition. Admin only."""
    if not await has_global_permission(current_user, Permission.MANAGE_DASHBOARD_WIDGETS, db):
        raise HTTPException(status_code=403, detail="Permission denied")
    return await _run_single_query(req, current_user, db)


@router.post("/widgets/query-preview-multi")
async def query_preview_multi(
    req: MultiQueryPreviewRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Preview N parallel sub-queries. Feeds compositional widgets
    (ratio, percentage, delta, overlay). Widget-management only — the
    per-widget runtime endpoint below handles operator-scoped reads.
    Runs each sub-query in the same session, then returns them in
    caller-supplied order so the frontend can do the arithmetic without
    a second round trip."""
    if not await has_global_permission(current_user, Permission.MANAGE_DASHBOARD_WIDGETS, db):
        raise HTTPException(status_code=403, detail="Permission denied")
    results = []
    for q in req.queries:
        results.append(await _run_single_query(q, current_user, db))
    return {"results": results}


@router.get("/widgets/{widget_id}/data")
async def get_widget_data(
    widget_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get data for a custom-query widget.

    Widget shapes:
      - Single-query: ``config.query = {...}`` — returns one result payload.
      - Composite:   ``config.queries = [{...}, {...}, ...]`` — returns
        ``{results: [...]}`` in the same order for ratio / percentage /
        delta / overlay widget types.
    """
    result = await db.execute(select(DashboardWidget).where(DashboardWidget.id == widget_id))
    widget = result.scalar_one_or_none()
    if not widget:
        raise HTTPException(404, "Widget not found")
    if widget.data_source != "custom_query":
        raise HTTPException(400, "Widget does not use custom_query data source")

    cfg = widget.config or {}
    # Composite path — carries N sub-queries.
    queries_config = cfg.get("queries")
    if queries_config:
        if not isinstance(queries_config, list) or not queries_config:
            raise HTTPException(400, "config.queries must be a non-empty list")
        if len(queries_config) > 6:
            raise HTTPException(400, "config.queries capped at 6 sub-queries")
        results = []
        for q_cfg in queries_config:
            sub_req = QueryPreviewRequest(**q_cfg)
            results.append(await _run_single_query(sub_req, current_user, db, scope_to_user=True))
        return {"results": results, "mode": "composite"}

    # Single-query path (legacy shape).
    query_config = cfg.get("query")
    if not query_config:
        return {"data": []}
    req = QueryPreviewRequest(**query_config)
    return await _run_single_query(req, current_user, db, scope_to_user=True)


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
            "joins": sorted({jt for (ft, jt) in _JOIN_PATHS.keys() if ft == table_name}),
            "sensitive": table_name in _SENSITIVE_TABLES,
        }
    return {
        "tables": list(_TABLE_MAP.keys()),
        "schema": schema,
        "aggregations": list(_AGG_FUNCS.keys()),
        "filter_operators": list(_FILTER_OPS.keys()),
        "date_ranges": ["7d", "30d", "90d", "quarter", "year", "all", "custom"],
        "time_buckets": ["day", "week", "month"],
        "sensitive_tables": sorted(_SENSITIVE_TABLES),
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
