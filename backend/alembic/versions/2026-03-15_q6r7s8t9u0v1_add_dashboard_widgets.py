"""Add dashboard widgets table and user dashboard_layout column.

Revision ID: q6r7s8t9u0v1
Revises: p5q6r7s8t9u0
Create Date: 2026-03-15
"""
from alembic import op
import sqlalchemy as sa

revision = "q6r7s8t9u0v1"
down_revision = "p5q6r7s8t9u0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Dashboard widgets table
    op.create_table(
        "dashboard_widgets",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("widget_type", sa.String(50), nullable=False),
        sa.Column("data_source", sa.String(100), nullable=False),
        sa.Column("size", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("category", sa.String(50), nullable=False, server_default="custom"),
        sa.Column("icon", sa.String(50), nullable=True),
        sa.Column("config", sa.JSON(), nullable=True),
        sa.Column("is_system", sa.Boolean(), server_default="false"),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column("created_by", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # User dashboard layout column
    op.add_column("users", sa.Column("dashboard_layout", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "dashboard_layout")
    op.drop_table("dashboard_widgets")
