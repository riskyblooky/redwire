"""add version_history table

Revision ID: e8f9a0b1c2d3
Revises: d7e8f9a0b1c2
Create Date: 2026-02-21
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON

# revision identifiers, used by Alembic.
revision = "e8f9a0b1c2d3"
down_revision = "d7e8f9a0b1c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "version_history",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("entity_type", sa.String(20), nullable=False, index=True),
        sa.Column("entity_id", sa.String(), nullable=False, index=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", JSON(), nullable=False),
        sa.Column("changed_fields", JSON(), nullable=False),
        sa.Column("changed_by", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    # Composite index for fast lookups
    op.create_index(
        "ix_version_history_entity",
        "version_history",
        ["entity_type", "entity_id", "version"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_version_history_entity", table_name="version_history")
    op.drop_table("version_history")
