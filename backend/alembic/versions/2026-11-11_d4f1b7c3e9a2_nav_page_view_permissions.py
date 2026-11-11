"""Grant the new main-nav page permissions so upgrades keep today's tabs.

Stats, Remediation, Templates, Tags, Clients and Planning had no permission
of their own: every user saw the first four, and Clients / Planning showed
by role (admin, read-only admin, team lead). They now each need a *_view
permission. The seeder never changes existing groups, so this grants them
once, preserving what people could see before:

- stats_view, remediation_view, template_view, tag_view → every group.
- client_view, planning_view → the "Team Leads" group and every group with
  a TEAM_LEAD-role member. (ADMIN / READ_ONLY_ADMIN bypass view permissions.)

Admins then hide a page from a group by removing its permission.

Revision ID: d4f1b7c3e9a2
Revises: c2e7a9d4b1f6
Create Date: 2026-11-11
"""

import json

import sqlalchemy as sa
from alembic import op

revision = "d4f1b7c3e9a2"
down_revision = "c2e7a9d4b1f6"
branch_labels = None
depends_on = None

EVERYONE = ["stats_view", "remediation_view", "template_view", "tag_view"]
MANAGERS = ["client_view", "planning_view"]


def _load(perms):
    if perms is None:
        return []
    return json.loads(perms) if isinstance(perms, str) else list(perms)


def _set(conn, group_id, perms, exists):
    payload = json.dumps(perms)
    if exists:
        conn.execute(sa.text("UPDATE group_permissions SET permissions = CAST(:p AS json) WHERE group_id = :g"),
                     {"p": payload, "g": group_id})
    else:
        conn.execute(sa.text("INSERT INTO group_permissions (group_id, permissions) VALUES (:g, CAST(:p AS json))"),
                     {"p": payload, "g": group_id})


def upgrade() -> None:
    conn = op.get_bind()
    manager_groups = {r[0] for r in conn.execute(sa.text(
        "SELECT g.id FROM groups g WHERE g.name = 'Team Leads' "
        "UNION SELECT ug.group_id FROM user_groups ug JOIN users u ON u.id = ug.user_id "
        "WHERE u.role::text = 'TEAM_LEAD'"))}
    rows = conn.execute(sa.text(
        "SELECT g.id, gp.permissions, gp.group_id IS NOT NULL FROM groups g "
        "LEFT JOIN group_permissions gp ON gp.group_id = g.id")).all()
    for group_id, perms, exists in rows:
        perms = _load(perms)
        add = EVERYONE + (MANAGERS if group_id in manager_groups else [])
        new = perms + [p for p in add if p not in perms]
        if new != perms or not exists:
            _set(conn, group_id, new, exists)


def downgrade() -> None:
    conn = op.get_bind()
    drop = set(EVERYONE + MANAGERS)
    for group_id, perms in conn.execute(sa.text("SELECT group_id, permissions FROM group_permissions")).all():
        perms = _load(perms)
        kept = [p for p in perms if p not in drop]
        if kept != perms:
            _set(conn, group_id, kept, True)
