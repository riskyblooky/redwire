"""chain_links — directed causal edges for attack chains

Creates the chain_links table: a polymorphic directed edge over
testcase / finding / vault_item. source → target reads as "source led to
target". engagement_id is a real FK (cascade); the (type, id) endpoints are
polymorphic and maintained by the app (delete-path sweeps + read-time skip).

Revision ID: f6a0d3e8c4b2
Revises: e5f9c2d7b3a1
"""
from alembic import op
import sqlalchemy as sa

revision = "f6a0d3e8c4b2"
down_revision = "e5f9c2d7b3a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "chain_links" in inspector.get_table_names():
        return

    op.create_table(
        "chain_links",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("engagement_id", sa.String(), nullable=False),
        sa.Column("source_type", sa.String(length=20), nullable=False),
        sa.Column("source_id", sa.String(), nullable=False),
        sa.Column("target_type", sa.String(length=20), nullable=False),
        sa.Column("target_id", sa.String(), nullable=False),
        sa.Column("relation", sa.String(length=30), nullable=False, server_default="led_to"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["engagement_id"], ["engagements.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "source_type", "source_id", "target_type", "target_id",
            name="uq_chain_link_edge",
        ),
    )
    op.create_index("ix_chain_links_engagement", "chain_links", ["engagement_id"])
    op.create_index("ix_chain_links_source_id", "chain_links", ["source_id"])
    op.create_index("ix_chain_links_target_id", "chain_links", ["target_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "chain_links" not in inspector.get_table_names():
        return
    op.drop_index("ix_chain_links_target_id", table_name="chain_links")
    op.drop_index("ix_chain_links_source_id", table_name="chain_links")
    op.drop_index("ix_chain_links_engagement", table_name="chain_links")
    op.drop_table("chain_links")
