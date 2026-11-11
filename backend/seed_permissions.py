"""
Seed default groups and engagement roles with appropriate permissions.
This should be run on application startup.
"""
import logging

from sqlalchemy import select
from database import AsyncSessionLocal
from models.group import Group
from models.engagement_role import EngagementRole
from models.permission import (
    Permission,
    GroupPermissions,
    EngagementRolePermissions
)

logger = logging.getLogger(__name__)


async def seed_default_groups_and_roles():
    """Seed default groups and roles if they don't exist."""
    
    async with AsyncSessionLocal() as db:
        # ============ Define Default Groups ============
        default_groups = [
            {
                "name": "Team Leads",
                "description": "Project leads who can create and manage engagements",
                "is_system": False,
                "is_default": False,
                "permissions": [
                    # Main-nav pages (the tab is hidden without these).
                    Permission.STATS_VIEW.value,
                    Permission.REMEDIATION_VIEW.value,
                    Permission.TEMPLATE_VIEW.value,
                    Permission.TAG_VIEW.value,
                    Permission.CLIENT_VIEW.value,
                    Permission.PLANNING_VIEW.value,
                    Permission.VIEW_ALL_USERS.value,
                    Permission.VIEW_ALL_ENGAGEMENTS.value,
                    Permission.CREATE_ENGAGEMENT.value,
                    Permission.MANAGE_FINDING_TEMPLATES.value,
                    Permission.MANAGE_TESTCASE_TEMPLATES.value,
                    Permission.MANAGE_REPORT_LAYOUT_TEMPLATES.value,
                    Permission.MANAGE_REPORT_THEMES.value,
                    Permission.VIEW_ALL_ANALYTICS.value,
                    Permission.CALENDAR_VIEW.value,
                    Permission.CALENDAR_CREATE.value,
                    Permission.CALENDAR_EDIT.value,
                    Permission.CALENDAR_DELETE.value,
                    Permission.AUTOMATION_VIEW.value,
                    Permission.AUTOMATION_CREATE.value,
                    Permission.AUTOMATION_EDIT.value,
                    Permission.INTEL_VIEW.value,
                    Permission.INTEL_CREATE.value,
                    Permission.INTEL_EDIT.value,
                    Permission.INTEL_DELETE.value,
                    Permission.INTEL_MANAGE_FEEDS.value,
                    Permission.INFRA_VIEW.value,
                    Permission.INFRA_CREATE.value,
                    Permission.INFRA_EDIT.value,
                    Permission.INFRA_DELETE.value,
                    Permission.SKILL_VIEW.value,
                    Permission.SKILL_CREATE.value,
                    Permission.SKILL_EDIT.value,
                    Permission.SKILL_DELETE.value,
                    Permission.SKILL_MANAGE_CATEGORIES.value,
                    Permission.RUNBOOK_VIEW.value,
                    Permission.RUNBOOK_CREATE.value,
                    Permission.RUNBOOK_EDIT.value,
                    Permission.RUNBOOK_DELETE.value,
                    Permission.MANAGE_DASHBOARD_WIDGETS.value,
                    # Marking/classification profiles were previously lead-accessible.
                    Permission.MANAGE_MARKING_PROFILES.value,
                ]
            },
            {
                "name": "Default",
                "description": "Default group for all new users",
                "is_system": True,
                "is_default": True,
                "permissions": [
                    # VIEW_ALL_ENGAGEMENTS deliberately NOT granted here: it grants
                    # platform-wide view of every engagement's findings/assets/vault/
                    # etc. (via the override map) plus proposed engagements. New users
                    # see only engagements they're assigned to (need-to-know); grant
                    # VIEW_ALL_ENGAGEMENTS via the Team Leads group or explicitly.
                    Permission.VIEW_ALL_USERS.value,
                    Permission.CALENDAR_VIEW.value,
                    Permission.CALENDAR_CREATE.value,
                    Permission.CALENDAR_EDIT.value,
                    Permission.CALENDAR_DELETE.value,
                    Permission.INTEL_VIEW.value,
                    Permission.INFRA_VIEW.value,
                    Permission.SKILL_VIEW.value,
                    Permission.RUNBOOK_VIEW.value,
                    # Main-nav pages (the tab is hidden without these).
                    Permission.STATS_VIEW.value,
                    Permission.REMEDIATION_VIEW.value,
                    Permission.TEMPLATE_VIEW.value,
                    Permission.TAG_VIEW.value,
                ]
            },
            {
                "name": "Read-Only Users",
                "description": "Users with view-only access to engagements they're assigned to",
                "is_system": False,
                "is_default": False,
                "permissions": [
                    Permission.VIEW_ALL_USERS.value,
                    Permission.CALENDAR_VIEW.value,
                    Permission.INTEL_VIEW.value,
                    Permission.INFRA_VIEW.value,
                    Permission.SKILL_VIEW.value,
                    Permission.RUNBOOK_VIEW.value,
                    # Main-nav pages (the tab is hidden without these).
                    Permission.STATS_VIEW.value,
                    Permission.REMEDIATION_VIEW.value,
                    Permission.TEMPLATE_VIEW.value,
                    Permission.TAG_VIEW.value,
                ]
            },
        ]
        
        # ============ Define Default Engagement Roles ============
        default_engagement_roles = [
            {
                "name": "Engagement Lead",
                "description": "Full control over engagement including member management",
                "permissions": [
                    # All engagement permissions
                    Permission.ENGAGEMENT_VIEW.value,
                    Permission.ENGAGEMENT_EDIT.value,
                    Permission.ENGAGEMENT_DELETE.value,
                    Permission.ENGAGEMENT_MANAGE_MEMBERS.value,
                    Permission.FINDING_VIEW.value,
                    Permission.FINDING_CREATE.value,
                    Permission.FINDING_EDIT.value,
                    Permission.FINDING_DELETE.value,
                    Permission.FINDING_EDIT_ANY.value,
                    Permission.FINDING_DELETE_ANY.value,
                    Permission.ASSET_VIEW.value,
                    Permission.ASSET_CREATE.value,
                    Permission.ASSET_EDIT.value,
                    Permission.ASSET_DELETE.value,
                    Permission.TESTCASE_VIEW.value,
                    Permission.TESTCASE_CREATE.value,
                    Permission.TESTCASE_EDIT.value,
                    Permission.TESTCASE_DELETE.value,
                    Permission.EVIDENCE_VIEW.value,
                    Permission.EVIDENCE_CREATE.value,
                    Permission.EVIDENCE_EDIT.value,
                    Permission.EVIDENCE_EDIT_ANY.value,
                    Permission.EVIDENCE_DELETE.value,
                    Permission.EVIDENCE_DELETE_ANY.value,
                    Permission.VAULT_VIEW.value,
                    Permission.VAULT_CREATE.value,
                    Permission.VAULT_EDIT.value,
                    Permission.VAULT_DELETE.value,
                    Permission.DISCUSSION_VIEW.value,
                    Permission.DISCUSSION_CREATE.value,
                    Permission.DISCUSSION_EDIT.value,
                    Permission.DISCUSSION_DELETE.value,
                    Permission.DISCUSSION_EDIT_ANY.value,
                    Permission.DISCUSSION_DELETE_ANY.value,
                    Permission.REPORT_VIEW.value,
                    Permission.REPORT_GENERATE.value,
                    Permission.NOTE_VIEW.value,
                    Permission.NOTE_CREATE.value,
                    Permission.NOTE_EDIT.value,
                    Permission.NOTE_DELETE.value,
                    Permission.NOTE_EDIT_ANY.value,
                    Permission.NOTE_DELETE_ANY.value,
                    Permission.CLEANUP_VIEW.value,
                    Permission.CLEANUP_CREATE.value,
                    Permission.CLEANUP_EDIT.value,
                    Permission.CLEANUP_DELETE.value,
                    Permission.CLEANUP_EDIT_ANY.value,
                    Permission.CLEANUP_DELETE_ANY.value,
                ]
            },
            {
                "name": "Operator",
                "description": "Standard operator with create/edit/delete on own resources",
                "permissions": [
                    Permission.ENGAGEMENT_VIEW.value,
                    Permission.FINDING_VIEW.value,
                    Permission.FINDING_CREATE.value,
                    Permission.FINDING_EDIT.value,
                    Permission.FINDING_DELETE.value,
                    Permission.ASSET_VIEW.value,
                    Permission.ASSET_CREATE.value,
                    Permission.ASSET_EDIT.value,
                    Permission.ASSET_DELETE.value,
                    Permission.TESTCASE_VIEW.value,
                    Permission.TESTCASE_CREATE.value,
                    Permission.TESTCASE_EDIT.value,
                    Permission.TESTCASE_DELETE.value,
                    Permission.EVIDENCE_VIEW.value,
                    Permission.EVIDENCE_CREATE.value,
                    Permission.EVIDENCE_EDIT.value,
                    Permission.EVIDENCE_DELETE.value,
                    Permission.VAULT_VIEW.value,
                    Permission.VAULT_CREATE.value,
                    Permission.VAULT_EDIT.value,
                    Permission.VAULT_DELETE.value,
                    Permission.DISCUSSION_VIEW.value,
                    Permission.DISCUSSION_CREATE.value,
                    Permission.DISCUSSION_EDIT.value,
                    Permission.DISCUSSION_DELETE.value,
                    Permission.REPORT_VIEW.value,
                    Permission.NOTE_VIEW.value,
                    Permission.NOTE_CREATE.value,
                    Permission.NOTE_EDIT.value,
                    Permission.NOTE_DELETE.value,
                    Permission.CLEANUP_VIEW.value,
                    Permission.CLEANUP_CREATE.value,
                    Permission.CLEANUP_EDIT.value,
                    Permission.CLEANUP_DELETE.value,
                ]
            },
            {
                "name": "Observer",
                "description": "View-only access to engagement resources",
                "permissions": [
                    Permission.ENGAGEMENT_VIEW.value,
                    Permission.FINDING_VIEW.value,
                    Permission.ASSET_VIEW.value,
                    Permission.TESTCASE_VIEW.value,
                    Permission.EVIDENCE_VIEW.value,
                    Permission.VAULT_VIEW.value,
                    Permission.DISCUSSION_VIEW.value,
                    Permission.REPORT_VIEW.value,
                    Permission.NOTE_VIEW.value,
                    Permission.CLEANUP_VIEW.value,
                ]
            },
        ]
        
        # ============ Seed Groups ============
        for group_data in default_groups:
            # Check if group exists
            result = await db.execute(
                select(Group).where(Group.name == group_data["name"])
            )
            existing_group = result.scalar_one_or_none()
            
            if not existing_group:
                # Create group
                new_group = Group(
                    name=group_data["name"],
                    description=group_data["description"],
                    is_system=group_data.get("is_system", False),
                    is_default=group_data.get("is_default", False),
                )
                db.add(new_group)
                await db.flush()
                
                # Create permissions
                group_perms = GroupPermissions(
                    group_id=new_group.id,
                    permissions=group_data["permissions"]
                )
                db.add(group_perms)
                print(f"✅ Created group: {group_data['name']}")
            else:
                # GHSA-28f5-4wcg-9pwv: leave existing groups untouched on
                # restart. The previous behaviour set-unioned the hard-coded
                # seed list back into the DB row on every boot and force-set
                # is_default=True, which silently re-granted permissions an
                # administrator had deliberately revoked and re-defaulted
                # groups the admin had un-defaulted. New permission constants
                # introduced by an upgrade no longer auto-land here — the
                # admin must add them via the admin UI, or a release ships
                # them as a SEED_REVISIONS entry (applied once, additively).
                #
                # The one remaining mutation: backfill the permissions row if
                # it's missing entirely (group row present but no
                # GroupPermissions). That isn't a revoke-revert; it's repair
                # for a deployment whose seed never finished.
                result = await db.execute(
                    select(GroupPermissions).where(GroupPermissions.group_id == existing_group.id)
                )
                existing_perms = result.scalar_one_or_none()
                if existing_perms:
                    logger.debug(
                        "seed_default_groups_and_roles: group %r exists, leaving permissions untouched",
                        group_data["name"],
                    )
                else:
                    group_perms = GroupPermissions(
                        group_id=existing_group.id,
                        permissions=group_data["permissions"]
                    )
                    db.add(group_perms)
                    print(f"🔄 Created missing permissions for group: {group_data['name']}")
        
        # ============ Seed Engagement Roles ============
        for role_data in default_engagement_roles:
            # Check if role exists
            result = await db.execute(
                select(EngagementRole).where(EngagementRole.name == role_data["name"])
            )
            existing_role = result.scalar_one_or_none()
            
            if not existing_role:
                # Create role
                new_role = EngagementRole(
                    name=role_data["name"],
                    description=role_data["description"]
                )
                db.add(new_role)
                await db.flush()
                
                # Create permissions
                role_perms = EngagementRolePermissions(
                    role_id=new_role.id,
                    permissions=role_data["permissions"]
                )
                db.add(role_perms)
                print(f"✅ Created engagement role: {role_data['name']}")
            else:
                # GHSA-28f5-4wcg-9pwv: same "no auto-merge into existing rows"
                # rule as the groups path above. Only backfill a missing
                # permissions row.
                result = await db.execute(
                    select(EngagementRolePermissions).where(EngagementRolePermissions.role_id == existing_role.id)
                )
                existing_perms = result.scalar_one_or_none()
                if existing_perms:
                    logger.debug(
                        "seed_default_groups_and_roles: engagement role %r exists, leaving permissions untouched",
                        role_data["name"],
                    )
                else:
                    role_perms = EngagementRolePermissions(
                        role_id=existing_role.id,
                        permissions=role_data["permissions"]
                    )
                    db.add(role_perms)
                    print(f"🔄 Created missing permissions for role: {role_data['name']}")
        
        await apply_seed_revisions(db)

        await db.commit()
        print("✅ Default groups and roles seeded/verified")


# ============ Seed revisions ============
# Existing groups/roles are never re-merged with the seed lists above
# (GHSA-28f5), so a permission a release adds to a default group would only
# reach fresh installs. Each SEED_REVISIONS entry is a one-shot, additive
# grant to the named default group / engagement role, applied once per
# deployment and tracked by the watermark in auth_settings. A grant an admin
# later revokes stays revoked: the revision never runs again.
#
# To ship a new default permission: add it to the seed list above AND append
# a new revision here. Never edit or renumber a released revision.
SEED_REVISIONS: list[dict] = [
    {
        # Permissions added to the seed lists after GHSA-28f5 (1.3.x–1.5.x)
        # that never reached existing deployments.
        "revision": 1,
        "groups": {
            "Team Leads": [Permission.MANAGE_MARKING_PROFILES.value],
        },
        "roles": {
            "Engagement Lead": [Permission.EVIDENCE_EDIT.value, Permission.EVIDENCE_EDIT_ANY.value],
            "Operator": [Permission.EVIDENCE_EDIT.value],
        },
    },
]

SEED_REVISION_KEY = "seed_permissions_revision"


async def apply_seed_revisions(db) -> int:
    """Apply SEED_REVISIONS above the stored watermark; returns the new watermark.
    Groups/roles that were renamed or deleted are skipped (nothing to grant to).
    """
    from models.auth_settings import AuthSetting

    setting = await db.get(AuthSetting, SEED_REVISION_KEY)
    try:
        current = int(setting.value) if setting and setting.value else 0
    except ValueError:
        current = 0
    pending = sorted((r for r in SEED_REVISIONS if r["revision"] > current), key=lambda r: r["revision"])
    if not pending:
        return current

    async def _grant(model, perms_model, fk, name, perms):
        row = (await db.execute(select(model).where(model.name == name))).scalar_one_or_none()
        if row is None:
            return
        pr = (await db.execute(select(perms_model).where(getattr(perms_model, fk) == row.id))).scalar_one_or_none()
        if pr is None:
            return
        have = list(pr.permissions or [])
        added = [p for p in perms if p not in have]
        if added:
            pr.permissions = have + added  # reassign so the JSON column is flagged dirty
            print(f"🔄 Seed revision: granted {', '.join(added)} to {name}")

    for rev in pending:
        for name, perms in rev.get("groups", {}).items():
            await _grant(Group, GroupPermissions, "group_id", name, perms)
        for name, perms in rev.get("roles", {}).items():
            await _grant(EngagementRole, EngagementRolePermissions, "role_id", name, perms)

    latest = pending[-1]["revision"]
    if setting is None:
        db.add(AuthSetting(key=SEED_REVISION_KEY, value=str(latest), is_encrypted=False))
    else:
        setting.value = str(latest)
    return latest

    # Configurable types are now seeded by seed_defaults.seed_all_defaults
    # — kept the function below for any one-off callers that might still
    # exercise it, but it's no longer chained from startup.


async def seed_default_configurable_types():
    """Seed default configurable types if they don't exist."""
    from models.configurable_type import ConfigurableType
    import uuid

    defaults = [
        # Asset types
        {"category": "asset", "name": "IP Address", "color": "#6366f1", "sort_order": 0},
        {"category": "asset", "name": "Domain", "color": "#8b5cf6", "sort_order": 1},
        {"category": "asset", "name": "URL", "color": "#a855f7", "sort_order": 2},
        {"category": "asset", "name": "Application", "color": "#d946ef", "sort_order": 3},
        {"category": "asset", "name": "Server", "color": "#ec4899", "sort_order": 4},
        {"category": "asset", "name": "Network", "color": "#f43f5e", "sort_order": 5},
        {"category": "asset", "name": "Other", "color": "#64748b", "sort_order": 6},
        # Engagement types
        {"category": "engagement", "name": "External Pentest", "color": "#ef4444", "sort_order": 0},
        {"category": "engagement", "name": "Internal Pentest", "color": "#f97316", "sort_order": 1},
        {"category": "engagement", "name": "Web Application", "color": "#eab308", "sort_order": 2},
        {"category": "engagement", "name": "Mobile Application", "color": "#22c55e", "sort_order": 3},
        {"category": "engagement", "name": "Social Engineering", "color": "#14b8a6", "sort_order": 4},
        {"category": "engagement", "name": "Physical Security", "color": "#3b82f6", "sort_order": 5},
        {"category": "engagement", "name": "Red Team", "color": "#dc2626", "sort_order": 6},
        {"category": "engagement", "name": "Purple Team", "color": "#7c3aed", "sort_order": 7},
        {"category": "engagement", "name": "Other", "color": "#64748b", "sort_order": 8},
        # Testcase categories
        {"category": "testcase", "name": "Reconnaissance", "color": "#6366f1", "sort_order": 0},
        {"category": "testcase", "name": "Scanning", "color": "#8b5cf6", "sort_order": 1},
        {"category": "testcase", "name": "Exploitation", "color": "#ef4444", "sort_order": 2},
        {"category": "testcase", "name": "Post Exploitation", "color": "#f97316", "sort_order": 3},
        {"category": "testcase", "name": "Privilege Escalation", "color": "#eab308", "sort_order": 4},
        {"category": "testcase", "name": "Persistence", "color": "#22c55e", "sort_order": 5},
        {"category": "testcase", "name": "Lateral Movement", "color": "#14b8a6", "sort_order": 6},
        {"category": "testcase", "name": "Web Application", "color": "#3b82f6", "sort_order": 7},
        {"category": "testcase", "name": "Social Engineering", "color": "#a855f7", "sort_order": 8},
        {"category": "testcase", "name": "Physical", "color": "#ec4899", "sort_order": 9},
        {"category": "testcase", "name": "Other", "color": "#64748b", "sort_order": 10},
        # Vault item types
        {"category": "vault", "name": "Credential", "color": "#6366f1", "sort_order": 0},
        {"category": "vault", "name": "Key", "color": "#8b5cf6", "sort_order": 1},
        {"category": "vault", "name": "File", "color": "#a855f7", "sort_order": 2},
        {"category": "vault", "name": "Note", "color": "#64748b", "sort_order": 3},
        # Cleanup artifact types
        {"category": "cleanup", "name": "SSH Key", "color": "#ef4444", "sort_order": 0},
        {"category": "cleanup", "name": "File", "color": "#f97316", "sort_order": 1},
        {"category": "cleanup", "name": "Account", "color": "#eab308", "sort_order": 2},
        {"category": "cleanup", "name": "Permission", "color": "#22c55e", "sort_order": 3},
        {"category": "cleanup", "name": "Backdoor", "color": "#dc2626", "sort_order": 4},
        {"category": "cleanup", "name": "Implant", "color": "#7c3aed", "sort_order": 5},
        {"category": "cleanup", "name": "Other", "color": "#64748b", "sort_order": 6},
        # Finding categories
        {"category": "finding", "name": "Web Application", "color": "#3b82f6", "sort_order": 0},
        {"category": "finding", "name": "Network", "color": "#6366f1", "sort_order": 1},
        {"category": "finding", "name": "Infrastructure", "color": "#8b5cf6", "sort_order": 2},
        {"category": "finding", "name": "Authentication", "color": "#ef4444", "sort_order": 3},
        {"category": "finding", "name": "Authorization", "color": "#f97316", "sort_order": 4},
        {"category": "finding", "name": "Cryptography", "color": "#eab308", "sort_order": 5},
        {"category": "finding", "name": "Configuration", "color": "#22c55e", "sort_order": 6},
        {"category": "finding", "name": "Information Disclosure", "color": "#14b8a6", "sort_order": 7},
        {"category": "finding", "name": "Injection", "color": "#dc2626", "sort_order": 8},
        {"category": "finding", "name": "Social Engineering", "color": "#a855f7", "sort_order": 9},
        {"category": "finding", "name": "Physical", "color": "#ec4899", "sort_order": 10},
        {"category": "finding", "name": "Other", "color": "#64748b", "sort_order": 11},
        # Intel item types
        {"category": "intel", "name": "CVE", "color": "#ef4444", "sort_order": 0},
        {"category": "intel", "name": "Advisory", "color": "#f97316", "sort_order": 1},
        {"category": "intel", "name": "Article", "color": "#3b82f6", "sort_order": 2},
        {"category": "intel", "name": "Zine", "color": "#8b5cf6", "sort_order": 3},
        {"category": "intel", "name": "Exploit", "color": "#dc2626", "sort_order": 4},
        {"category": "intel", "name": "Other", "color": "#64748b", "sort_order": 5},
        # Infrastructure types
        {"category": "infra", "name": "VPS", "color": "#3b82f6", "sort_order": 0},
        {"category": "infra", "name": "C2", "color": "#ef4444", "sort_order": 1},
        {"category": "infra", "name": "Redirector", "color": "#f97316", "sort_order": 2},
        {"category": "infra", "name": "Proxy", "color": "#eab308", "sort_order": 3},
        {"category": "infra", "name": "Phishing", "color": "#a855f7", "sort_order": 4},
        {"category": "infra", "name": "Jumpbox", "color": "#22c55e", "sort_order": 5},
        {"category": "infra", "name": "Other", "color": "#64748b", "sort_order": 6},
        # Runbook types
        {"category": "runbook", "name": "External Pentest", "color": "#ef4444", "sort_order": 0},
        {"category": "runbook", "name": "Internal Pentest", "color": "#f97316", "sort_order": 1},
        {"category": "runbook", "name": "Web Application", "color": "#3b82f6", "sort_order": 2},
        {"category": "runbook", "name": "Mobile Application", "color": "#22c55e", "sort_order": 3},
        {"category": "runbook", "name": "Red Team", "color": "#dc2626", "sort_order": 4},
        {"category": "runbook", "name": "Social Engineering", "color": "#a855f7", "sort_order": 5},
        {"category": "runbook", "name": "Physical Security", "color": "#ec4899", "sort_order": 6},
        {"category": "runbook", "name": "Wireless", "color": "#14b8a6", "sort_order": 7},
        {"category": "runbook", "name": "Cloud", "color": "#6366f1", "sort_order": 8},
        {"category": "runbook", "name": "Other", "color": "#64748b", "sort_order": 9},
    ]

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ConfigurableType.category, ConfigurableType.name)
        )
        existing = {(row[0], row[1]) for row in result.all()}

        added = 0
        for t in defaults:
            if (t["category"], t["name"]) not in existing:
                db.add(ConfigurableType(
                    id=str(uuid.uuid4()),
                    category=t["category"],
                    name=t["name"],
                    color=t.get("color", "#6366f1"),
                    is_system=True,
                    sort_order=t["sort_order"],
                ))
                added += 1

        if added:
            await db.commit()
            print(f"✅ Seeded {added} default configurable types")
        else:
            print("✅ Configurable types already present")

