"""markdown_images.scope — library images for engagement-less editors

Revision ID: c9e5a1f3b4d6
Revises: b8d4f0e2a3c5
Create Date: 2026-11-05
"""
from alembic import op
import sqlalchemy as sa

revision = "c9e5a1f3b4d6"
down_revision = "b8d4f0e2a3c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "markdown_images",
        sa.Column("scope", sa.String(20), nullable=False, server_default="engagement"),
    )
    op.alter_column("markdown_images", "engagement_id", existing_type=sa.String(), nullable=True)
    op.create_check_constraint(
        "ck_markdown_images_scope",
        "markdown_images",
        "(scope = 'engagement' AND engagement_id IS NOT NULL) OR "
        "(scope = 'library' AND engagement_id IS NULL)",
    )


def downgrade() -> None:
    op.execute("DELETE FROM markdown_images WHERE scope = 'library'")
    op.drop_constraint("ck_markdown_images_scope", "markdown_images", type_="check")
    op.alter_column("markdown_images", "engagement_id", existing_type=sa.String(), nullable=False)
    op.drop_column("markdown_images", "scope")
