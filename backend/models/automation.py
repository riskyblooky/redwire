from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey, Text, Integer, JSON
from database import Base
from datetime import datetime
import uuid


class AutomationRule(Base):
    __tablename__ = "automation_rules"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    trigger_type = Column(String(64), nullable=False, index=True)
    conditions = Column(JSON, nullable=False, default=list)   # [{field, operator, value}]
    actions = Column(JSON, nullable=False, default=list)       # [{type, ...config}]
    is_enabled = Column(Boolean, default=True, nullable=False)
    created_by = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_triggered_at = Column(DateTime, nullable=True)
    trigger_count = Column(Integer, default=0, nullable=False)


# All trigger types the engine understands.
# `fields` are surfaced in the UI as filterable dropdowns. `tags` and
# `cvss_score` rely on extra_context being populated by the corresponding
# router (see findings.py / testcases.py).
TRIGGER_TYPES = {
    "created_finding": {
        "label": "Finding Created",
        "icon": "🔍",
        "fields": ["severity", "status", "tags", "cvss_score", "engagement_id", "resource_name"],
    },
    "updated_finding": {
        "label": "Finding Updated",
        "icon": "✏️",
        "fields": ["severity", "status", "tags", "cvss_score", "engagement_id", "resource_name"],
    },
    "finding_status_changed": {
        "label": "Finding Status Changed",
        "icon": "🔄",
        "fields": ["severity", "status", "tags", "cvss_score", "engagement_id", "resource_name"],
    },
    "created_engagement": {
        "label": "Engagement Created",
        "icon": "📋",
        "fields": ["engagement_id", "resource_name"],
    },
    "updated_engagement": {
        "label": "Engagement Updated",
        "icon": "✏️",
        "fields": ["engagement_id", "resource_name"],
    },
    "engagement_status_changed": {
        "label": "Engagement Status Changed",
        "icon": "📋",
        "fields": ["status", "engagement_id", "resource_name"],
    },
    "created_testcase": {
        "label": "Test Case Created",
        "icon": "🧪",
        "fields": ["tags", "engagement_id", "resource_name"],
    },
    "updated_testcase": {
        "label": "Test Case Updated",
        "icon": "✏️",
        "fields": ["tags", "engagement_id", "resource_name"],
    },
    "executed_testcase": {
        "label": "Test Case Executed",
        "icon": "✅",
        "fields": ["tags", "engagement_id", "resource_name"],
    },
    "created_asset": {
        "label": "Asset Created",
        "icon": "🖥️",
        "fields": ["asset_type", "engagement_id", "resource_name"],
    },
    "updated_asset": {
        "label": "Asset Updated",
        "icon": "🖥️",
        "fields": ["asset_type", "engagement_id", "resource_name"],
    },
    "uploaded_evidence": {
        "label": "Evidence Uploaded",
        "icon": "📎",
        "fields": ["engagement_id", "resource_name"],
    },
    "created_comment": {
        "label": "Comment Created",
        "icon": "💬",
        "fields": ["engagement_id", "resource_name"],
    },
    "created_note": {
        "label": "Note Created",
        "icon": "📝",
        "fields": ["engagement_id", "resource_name"],
    },
    "created_vault_item": {
        "label": "Vault Item Created",
        "icon": "🔐",
        "fields": ["engagement_id", "resource_name"],
    },
    "created_cleanup_artifact": {
        "label": "Cleanup Item Created",
        "icon": "🧹",
        "fields": ["engagement_id", "resource_name"],
    },
    "updated_cleanup_artifact": {
        "label": "Cleanup Item Updated",
        "icon": "🧹",
        "fields": ["status", "engagement_id", "resource_name"],
    },
    "cleanup_status_changed": {
        "label": "Cleanup Status Changed",
        "icon": "🔄",
        "fields": ["status", "engagement_id", "resource_name"],
    },
    "assigned_user": {
        "label": "User Assigned to Engagement",
        "icon": "👥",
        "fields": ["engagement_id", "resource_name"],
    },
    "removed_user": {
        "label": "User Removed from Engagement",
        "icon": "🚫",
        "fields": ["engagement_id", "resource_name"],
    },
    "manual": {
        "label": "Manual Only",
        "icon": "▶️",
        "fields": [],
    },
}
