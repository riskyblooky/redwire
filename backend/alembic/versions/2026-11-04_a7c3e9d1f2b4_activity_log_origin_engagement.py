"""activity_logs.origin_engagement_id — keep the engagement link after deletion

Revision ID: a7c3e9d1f2b4
Revises: 147d557d7adc
Create Date: 2026-11-04
"""
from alembic import op
import sqlalchemy as sa

revision = "a7c3e9d1f2b4"
down_revision = "147d557d7adc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("activity_logs", sa.Column("origin_engagement_id", sa.String(), nullable=True))
    op.create_index("ix_activity_logs_origin_engagement_id", "activity_logs", ["origin_engagement_id"])
    # Live rows: copy the current link.
    op.execute("UPDATE activity_logs SET origin_engagement_id = engagement_id WHERE engagement_id IS NOT NULL")
    # Deletion tombstones already orphaned: their resource_id is the engagement id.
    # (Other rows orphaned before this migration can't be attributed.)
    op.execute(
        "UPDATE activity_logs SET origin_engagement_id = resource_id "
        "WHERE engagement_id IS NULL AND action = 'deleted_engagement'"
    )


def downgrade() -> None:
    op.drop_index("ix_activity_logs_origin_engagement_id", table_name="activity_logs")
    op.drop_column("activity_logs", "origin_engagement_id")
