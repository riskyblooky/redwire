from sqlalchemy import Column, String, ForeignKey, JSON
from sqlalchemy.orm import relationship
from database import Base
import uuid
import enum

class Permission(str, enum.Enum):
    """Comprehensive permission enumeration for RBAC system."""
    
    # ============ Global Site Permissions ============
    # User Management
    MANAGE_USERS = "manage_users"
    VIEW_ALL_USERS = "view_all_users"
    
    # Group & Role Management
    MANAGE_GROUPS = "manage_groups"
    MANAGE_ENGAGEMENT_ROLES = "manage_engagement_roles"
    
    # Registration & Access
    MANAGE_REGISTRATION_CODES = "manage_registration_codes"
    
    # Engagement Global Permissions
    VIEW_ALL_ENGAGEMENTS = "view_all_engagements"
    CREATE_ENGAGEMENT = "create_engagement"
    DELETE_ANY_ENGAGEMENT = "delete_any_engagement"
    
    # Templates
    MANAGE_FINDING_TEMPLATES = "manage_finding_templates"
    MANAGE_TESTCASE_TEMPLATES = "manage_testcase_templates"
    MANAGE_REPORT_LAYOUT_TEMPLATES = "manage_report_layout_templates"
    MANAGE_REPORT_THEMES = "manage_report_themes"
    
    # Tags
    MANAGE_TAGS = "manage_tags"
    
    # Clients
    MANAGE_CLIENTS = "manage_clients"
    MANAGE_CLIENT_ACCESS = "manage_client_access"
    
    # Analytics
    VIEW_ALL_ANALYTICS = "view_all_analytics"
    
    # ============ Engagement-Specific Permissions ============
    # Engagement Management
    ENGAGEMENT_VIEW = "engagement_view"
    ENGAGEMENT_EDIT = "engagement_edit"
    ENGAGEMENT_DELETE = "engagement_delete"
    ENGAGEMENT_MANAGE_MEMBERS = "engagement_manage_members"
    
    # Findings
    FINDING_VIEW = "finding_view"
    FINDING_CREATE = "finding_create"
    FINDING_EDIT = "finding_edit"
    FINDING_DELETE = "finding_delete"
    FINDING_EDIT_ANY = "finding_edit_any"  # Edit any finding, not just own
    FINDING_DELETE_ANY = "finding_delete_any"  # Delete any finding
    
    # Assets
    ASSET_VIEW = "asset_view"
    ASSET_CREATE = "asset_create"
    ASSET_EDIT = "asset_edit"
    ASSET_DELETE = "asset_delete"
    ASSET_EDIT_ANY = "asset_edit_any"  # Edit any asset, not just own
    ASSET_DELETE_ANY = "asset_delete_any"  # Delete any asset
    
    # Test Cases
    TESTCASE_VIEW = "testcase_view"
    TESTCASE_CREATE = "testcase_create"
    TESTCASE_EDIT = "testcase_edit"
    TESTCASE_DELETE = "testcase_delete"
    TESTCASE_EDIT_ANY = "testcase_edit_any"  # Edit any test case, not just own
    TESTCASE_DELETE_ANY = "testcase_delete_any"  # Delete any test case
    
    # Evidence
    EVIDENCE_VIEW = "evidence_view"
    EVIDENCE_CREATE = "evidence_create"
    EVIDENCE_EDIT = "evidence_edit"
    EVIDENCE_DELETE = "evidence_delete"
    EVIDENCE_EDIT_ANY = "evidence_edit_any"  # Edit any evidence, not just own
    EVIDENCE_DELETE_ANY = "evidence_delete_any"  # Delete any evidence
    
    # Vault
    VAULT_VIEW = "vault_view"
    VAULT_CREATE = "vault_create"
    VAULT_EDIT = "vault_edit"
    VAULT_DELETE = "vault_delete"
    VAULT_EDIT_ANY = "vault_edit_any"  # Edit any vault item, not just own
    VAULT_DELETE_ANY = "vault_delete_any"  # Delete any vault item
    
    # Discussions
    DISCUSSION_VIEW = "discussion_view"
    DISCUSSION_CREATE = "discussion_create"
    DISCUSSION_EDIT = "discussion_edit"
    DISCUSSION_DELETE = "discussion_delete"
    DISCUSSION_EDIT_ANY = "discussion_edit_any"
    DISCUSSION_DELETE_ANY = "discussion_delete_any"
    
    # Calendar
    CALENDAR_VIEW = "calendar_view"
    CALENDAR_CREATE = "calendar_create"
    CALENDAR_EDIT = "calendar_edit"
    CALENDAR_DELETE = "calendar_delete"
    
    # Reports
    REPORT_VIEW = "report_view"
    REPORT_GENERATE = "report_generate"
    
    # Notes
    NOTE_VIEW = "note_view"
    NOTE_CREATE = "note_create"
    NOTE_EDIT = "note_edit"
    NOTE_DELETE = "note_delete"
    NOTE_EDIT_ANY = "note_edit_any"  # Edit any note, not just own
    NOTE_DELETE_ANY = "note_delete_any"  # Delete any note

    # Cleanup Artifacts
    CLEANUP_VIEW = "cleanup_view"
    CLEANUP_CREATE = "cleanup_create"
    CLEANUP_EDIT = "cleanup_edit"
    CLEANUP_DELETE = "cleanup_delete"
    CLEANUP_EDIT_ANY = "cleanup_edit_any"  # Edit any cleanup artifact, not just own
    CLEANUP_DELETE_ANY = "cleanup_delete_any"  # Delete any cleanup artifact

    # Automations
    AUTOMATION_VIEW = "automation_view"
    AUTOMATION_CREATE = "automation_create"
    AUTOMATION_EDIT = "automation_edit"
    AUTOMATION_DELETE = "automation_delete"

    # Intelligence
    INTEL_VIEW = "intel_view"
    INTEL_CREATE = "intel_create"
    INTEL_EDIT = "intel_edit"
    INTEL_DELETE = "intel_delete"
    INTEL_MANAGE_FEEDS = "intel_manage_feeds"

    # Infrastructure
    INFRA_VIEW = "infra_view"
    INFRA_CREATE = "infra_create"
    INFRA_EDIT = "infra_edit"
    INFRA_DELETE = "infra_delete"
    INFRA_VAULT_VIEW = "infra_vault_view"
    INFRA_VAULT_MANAGE = "infra_vault_manage"

    # Skills
    SKILL_VIEW = "skill_view"
    SKILL_CREATE = "skill_create"
    SKILL_EDIT = "skill_edit"
    SKILL_DELETE = "skill_delete"
    SKILL_MANAGE_CATEGORIES = "skill_manage_categories"

    # Runbooks
    RUNBOOK_VIEW = "runbook_view"
    RUNBOOK_CREATE = "runbook_create"
    RUNBOOK_EDIT = "runbook_edit"
    RUNBOOK_DELETE = "runbook_delete"

    # Dashboard & Stats
    MANAGE_DASHBOARD_WIDGETS = "manage_dashboard_widgets"  # CRUD widget definitions + query builder
    CUSTOMIZE_DASHBOARD = "customize_dashboard"  # User: customize own layout
    MANAGE_STATS_PAGES = "manage_stats_pages"  # Create/arrange global stats-page tabs


class GroupPermissions(Base):
    """Stores permissions for site-wide groups."""
    __tablename__ = "group_permissions"
    
    group_id = Column(String, ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True)
    permissions = Column(JSON, nullable=False, default=list)  # List of permission strings
    
    # Relationships
    group = relationship("Group", back_populates="permission_set")


class EngagementRolePermissions(Base):
    """Stores permissions for engagement-specific roles."""
    __tablename__ = "engagement_role_permissions"
    
    role_id = Column(String, ForeignKey("engagement_roles.id", ondelete="CASCADE"), primary_key=True)
    permissions = Column(JSON, nullable=False, default=list)  # List of permission strings
    
    # Relationships
    role = relationship("EngagementRole", back_populates="permission_set")


# Permission categories for UI organization
PERMISSION_CATEGORIES = {
    "User & Access Management": [
        Permission.MANAGE_USERS,
        Permission.VIEW_ALL_USERS,
        Permission.MANAGE_GROUPS,
        Permission.MANAGE_ENGAGEMENT_ROLES,
        Permission.MANAGE_REGISTRATION_CODES,
        Permission.MANAGE_CLIENTS,
        Permission.MANAGE_CLIENT_ACCESS,
    ],
    "Engagements": [
        Permission.VIEW_ALL_ENGAGEMENTS,
        Permission.CREATE_ENGAGEMENT,
        Permission.DELETE_ANY_ENGAGEMENT,
        Permission.ENGAGEMENT_VIEW,
        Permission.ENGAGEMENT_EDIT,
        Permission.ENGAGEMENT_DELETE,
        Permission.ENGAGEMENT_MANAGE_MEMBERS,
    ],
    "Findings": [
        Permission.FINDING_VIEW,
        Permission.FINDING_CREATE,
        Permission.FINDING_EDIT,
        Permission.FINDING_DELETE,
        Permission.FINDING_EDIT_ANY,
        Permission.FINDING_DELETE_ANY,
    ],
    "Assets": [
        Permission.ASSET_VIEW,
        Permission.ASSET_CREATE,
        Permission.ASSET_EDIT,
        Permission.ASSET_DELETE,
        Permission.ASSET_EDIT_ANY,
        Permission.ASSET_DELETE_ANY,
    ],
    "Test Cases": [
        Permission.TESTCASE_VIEW,
        Permission.TESTCASE_CREATE,
        Permission.TESTCASE_EDIT,
        Permission.TESTCASE_DELETE,
        Permission.TESTCASE_EDIT_ANY,
        Permission.TESTCASE_DELETE_ANY,
    ],
    "Evidence": [
        Permission.EVIDENCE_VIEW,
        Permission.EVIDENCE_CREATE,
        Permission.EVIDENCE_EDIT,
        Permission.EVIDENCE_DELETE,
        Permission.EVIDENCE_EDIT_ANY,
        Permission.EVIDENCE_DELETE_ANY,
    ],
    "Vault": [
        Permission.VAULT_VIEW,
        Permission.VAULT_CREATE,
        Permission.VAULT_EDIT,
        Permission.VAULT_DELETE,
        Permission.VAULT_EDIT_ANY,
        Permission.VAULT_DELETE_ANY,
    ],
    "Discussions": [
        Permission.DISCUSSION_VIEW,
        Permission.DISCUSSION_CREATE,
        Permission.DISCUSSION_EDIT,
        Permission.DISCUSSION_DELETE,
        Permission.DISCUSSION_EDIT_ANY,
        Permission.DISCUSSION_DELETE_ANY,
    ],
    "Calendar": [
        Permission.CALENDAR_VIEW,
        Permission.CALENDAR_CREATE,
        Permission.CALENDAR_EDIT,
        Permission.CALENDAR_DELETE,
    ],
    "Reports & Templates": [
        Permission.REPORT_VIEW,
        Permission.REPORT_GENERATE,
        Permission.MANAGE_FINDING_TEMPLATES,
        Permission.MANAGE_TESTCASE_TEMPLATES,
        Permission.MANAGE_REPORT_LAYOUT_TEMPLATES,
        Permission.MANAGE_REPORT_THEMES,
        Permission.MANAGE_TAGS,
    ],
    "Analytics": [
        Permission.VIEW_ALL_ANALYTICS,
    ],
    "Dashboard & Stats": [
        Permission.MANAGE_DASHBOARD_WIDGETS,
        Permission.CUSTOMIZE_DASHBOARD,
        Permission.MANAGE_STATS_PAGES,
    ],
    "Notes": [
        Permission.NOTE_VIEW,
        Permission.NOTE_CREATE,
        Permission.NOTE_EDIT,
        Permission.NOTE_DELETE,
        Permission.NOTE_EDIT_ANY,
        Permission.NOTE_DELETE_ANY,
    ],
    "Cleanup Artifacts": [
        Permission.CLEANUP_VIEW,
        Permission.CLEANUP_CREATE,
        Permission.CLEANUP_EDIT,
        Permission.CLEANUP_DELETE,
        Permission.CLEANUP_EDIT_ANY,
        Permission.CLEANUP_DELETE_ANY,
    ],
    "Automations": [
        Permission.AUTOMATION_VIEW,
        Permission.AUTOMATION_CREATE,
        Permission.AUTOMATION_EDIT,
        Permission.AUTOMATION_DELETE,
    ],
    "Intelligence": [
        Permission.INTEL_VIEW,
        Permission.INTEL_CREATE,
        Permission.INTEL_EDIT,
        Permission.INTEL_DELETE,
        Permission.INTEL_MANAGE_FEEDS,
    ],
    "Infrastructure": [
        Permission.INFRA_VIEW,
        Permission.INFRA_CREATE,
        Permission.INFRA_EDIT,
        Permission.INFRA_DELETE,
        Permission.INFRA_VAULT_VIEW,
        Permission.INFRA_VAULT_MANAGE,
    ],
    "Skills": [
        Permission.SKILL_VIEW,
        Permission.SKILL_CREATE,
        Permission.SKILL_EDIT,
        Permission.SKILL_DELETE,
        Permission.SKILL_MANAGE_CATEGORIES,
    ],
    "Runbooks": [
        Permission.RUNBOOK_VIEW,
        Permission.RUNBOOK_CREATE,
        Permission.RUNBOOK_EDIT,
        Permission.RUNBOOK_DELETE,
    ],
}

# Global vs Engagement permission groups
GLOBAL_PERMISSIONS = [
    Permission.MANAGE_USERS,
    Permission.VIEW_ALL_USERS,
    Permission.MANAGE_GROUPS,
    Permission.MANAGE_ENGAGEMENT_ROLES,
    Permission.MANAGE_REGISTRATION_CODES,
    Permission.VIEW_ALL_ENGAGEMENTS,
    Permission.CREATE_ENGAGEMENT,
    Permission.DELETE_ANY_ENGAGEMENT,
    Permission.MANAGE_FINDING_TEMPLATES,
    Permission.MANAGE_TESTCASE_TEMPLATES,
    Permission.MANAGE_REPORT_LAYOUT_TEMPLATES,
    Permission.MANAGE_REPORT_THEMES,
    Permission.MANAGE_TAGS,
    Permission.MANAGE_CLIENTS,
    Permission.MANAGE_CLIENT_ACCESS,
    Permission.VIEW_ALL_ANALYTICS,
    Permission.CALENDAR_VIEW,
    Permission.CALENDAR_CREATE,
    Permission.CALENDAR_EDIT,
    Permission.CALENDAR_DELETE,
    Permission.AUTOMATION_VIEW,
    Permission.AUTOMATION_CREATE,
    Permission.AUTOMATION_EDIT,
    Permission.AUTOMATION_DELETE,
    Permission.INTEL_VIEW,
    Permission.INTEL_CREATE,
    Permission.INTEL_EDIT,
    Permission.INTEL_DELETE,
    Permission.INTEL_MANAGE_FEEDS,
    Permission.INFRA_VIEW,
    Permission.INFRA_CREATE,
    Permission.INFRA_EDIT,
    Permission.INFRA_DELETE,
    Permission.INFRA_VAULT_VIEW,
    Permission.INFRA_VAULT_MANAGE,
    Permission.SKILL_VIEW,
    Permission.SKILL_CREATE,
    Permission.SKILL_EDIT,
    Permission.SKILL_DELETE,
    Permission.SKILL_MANAGE_CATEGORIES,
    Permission.RUNBOOK_VIEW,
    Permission.RUNBOOK_CREATE,
    Permission.RUNBOOK_EDIT,
    Permission.RUNBOOK_DELETE,
    # Dashboard & Stats. These were previously declared in the Permission
    # enum but never listed here, so has_global_permission() rejected any
    # group grant of them (the `permission not in GLOBAL_PERMISSIONS: return
    # False` gate) — making them silently ADMIN-only and impossible to
    # delegate. Wiring them in makes them grantable via the permission-group
    # admin UI, which is what a "stats curator" role needs.
    Permission.MANAGE_DASHBOARD_WIDGETS,
    Permission.CUSTOMIZE_DASHBOARD,
    Permission.MANAGE_STATS_PAGES,
]

ENGAGEMENT_PERMISSIONS = [
    Permission.ENGAGEMENT_VIEW,
    Permission.ENGAGEMENT_EDIT,
    Permission.ENGAGEMENT_DELETE,
    Permission.ENGAGEMENT_MANAGE_MEMBERS,
    Permission.FINDING_VIEW,
    Permission.FINDING_CREATE,
    Permission.FINDING_EDIT,
    Permission.FINDING_DELETE,
    Permission.FINDING_EDIT_ANY,
    Permission.FINDING_DELETE_ANY,
    Permission.ASSET_VIEW,
    Permission.ASSET_CREATE,
    Permission.ASSET_EDIT,
    Permission.ASSET_DELETE,
    Permission.ASSET_EDIT_ANY,
    Permission.ASSET_DELETE_ANY,
    Permission.TESTCASE_VIEW,
    Permission.TESTCASE_CREATE,
    Permission.TESTCASE_EDIT,
    Permission.TESTCASE_DELETE,
    Permission.TESTCASE_EDIT_ANY,
    Permission.TESTCASE_DELETE_ANY,
    Permission.EVIDENCE_VIEW,
    Permission.EVIDENCE_CREATE,
    Permission.EVIDENCE_EDIT,
    Permission.EVIDENCE_DELETE,
    Permission.EVIDENCE_EDIT_ANY,
    Permission.EVIDENCE_DELETE_ANY,
    Permission.VAULT_VIEW,
    Permission.VAULT_CREATE,
    Permission.VAULT_EDIT,
    Permission.VAULT_DELETE,
    Permission.VAULT_EDIT_ANY,
    Permission.VAULT_DELETE_ANY,
    Permission.DISCUSSION_VIEW,
    Permission.DISCUSSION_CREATE,
    Permission.DISCUSSION_EDIT,
    Permission.DISCUSSION_DELETE,
    Permission.DISCUSSION_EDIT_ANY,
    Permission.DISCUSSION_DELETE_ANY,
    Permission.REPORT_VIEW,
    Permission.REPORT_GENERATE,
    Permission.NOTE_VIEW,
    Permission.NOTE_CREATE,
    Permission.NOTE_EDIT,
    Permission.NOTE_DELETE,
    Permission.NOTE_EDIT_ANY,
    Permission.NOTE_DELETE_ANY,
    Permission.CLEANUP_VIEW,
    Permission.CLEANUP_CREATE,
    Permission.CLEANUP_EDIT,
    Permission.CLEANUP_DELETE,
    Permission.CLEANUP_EDIT_ANY,
    Permission.CLEANUP_DELETE_ANY,
]
