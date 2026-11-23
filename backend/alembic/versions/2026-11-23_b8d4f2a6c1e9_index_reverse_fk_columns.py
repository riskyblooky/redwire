"""index foreign-key columns that had no leading index

spray_results.campaign_id (every campaign's result list and cascade delete),
runbook_items.template_id, user_groups.group_id (group member counts and
deletes), engagement_assignments.role_id, and the reverse side of four link
tables whose composite primary key starts with the other column.

Revision ID: b8d4f2a6c1e9
Revises: a3e7c1d9f4b2
Create Date: 2026-11-23
"""
from alembic import op

revision = "b8d4f2a6c1e9"
down_revision = "a3e7c1d9f4b2"
branch_labels = None
depends_on = None

_INDEXES = [
    ("spray_results", "campaign_id"),
    ("runbook_items", "template_id"),
    ("user_groups", "group_id"),
    ("engagement_assignments", "role_id"),
    ("note_vault_items", "vault_item_id"),
    ("note_cleanup_artifacts", "cleanup_artifact_id"),
    ("intel_item_notes", "note_id"),
    ("infra_item_notes", "note_id"),
]


def upgrade():
    for table, col in _INDEXES:
        op.create_index(f"ix_{table}_{col}", table, [col], if_not_exists=True)


def downgrade():
    for table, col in reversed(_INDEXES):
        op.drop_index(f"ix_{table}_{col}", table_name=table, if_exists=True)
