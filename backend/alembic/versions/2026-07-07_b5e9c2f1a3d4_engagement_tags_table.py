"""engagement_tags — many-to-many between engagements and tags

Mirrors finding_tags / testcase_tags so an engagement can carry the same
global tags an operator already uses on findings and test cases.
Composite PK (engagement_id, tag_id); both FKs ON DELETE CASCADE so a
deleted engagement or tag cleans up the join rows.

Revision ID: b5e9c2f1a3d4
Revises: a4c8f5d7e2b9
"""
from alembic import op
import sqlalchemy as sa

revision = "b5e9c2f1a3d4"
down_revision = "a4c8f5d7e2b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "engagement_tags" in inspector.get_table_names():
        return

    op.create_table(
        "engagement_tags",
        sa.Column("engagement_id", sa.String(), nullable=False),
        sa.Column("tag_id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["engagement_id"], ["engagements.id"], ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tag_id"], ["tags.id"], ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("engagement_id", "tag_id"),
    )
    op.create_index(
        "ix_engagement_tags_tag_id", "engagement_tags", ["tag_id"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "engagement_tags" not in inspector.get_table_names():
        return
    op.drop_index("ix_engagement_tags_tag_id", table_name="engagement_tags")
    op.drop_table("engagement_tags")
