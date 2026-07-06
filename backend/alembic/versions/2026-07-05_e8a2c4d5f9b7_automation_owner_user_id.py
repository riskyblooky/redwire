"""automation_rules: add owner_user_id for per-user personal rules

NULL owner_user_id preserves existing org/admin-scope semantics; a non-NULL
value scopes the rule to a single owner. The engine gates dispatch on
context.user_id == owner_user_id for personal rules; the router bypasses
AUTOMATION_CREATE / AUTOMATION_EDIT / AUTOMATION_DELETE gates when the
current user is the owner. ON DELETE CASCADE cleans up personal rules when
their owner is deleted.

Revision ID: e8a2c4d5f9b7
Revises: d347b4e5f6a1
"""
from alembic import op
import sqlalchemy as sa

revision = "e8a2c4d5f9b7"
down_revision = "d347b4e5f6a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "automation_rules",
        sa.Column("owner_user_id", sa.String(), nullable=True),
    )
    op.create_foreign_key(
        "fk_automation_rules_owner_user_id_users",
        "automation_rules",
        "users",
        ["owner_user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_automation_rules_owner_user_id",
        "automation_rules",
        ["owner_user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_automation_rules_owner_user_id", table_name="automation_rules")
    op.drop_constraint(
        "fk_automation_rules_owner_user_id_users",
        "automation_rules",
        type_="foreignkey",
    )
    op.drop_column("automation_rules", "owner_user_id")
