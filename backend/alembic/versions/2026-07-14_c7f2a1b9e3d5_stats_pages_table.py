"""stats_pages — global, shared, tabbed stats pages

Backs the tabbed /stats view. Each row is a tab with a page-owned shared
`layout` (list of {widget_id,x,y,w,h}) referencing the existing global
DashboardWidget definitions — no per-page widget-membership table, the
layout IS the membership (same as the dashboard). Layout is shared: an
editor's change is what every viewer sees. Seeds one empty "Overview" page
so the UI has a tab on first load.

Revision ID: c7f2a1b9e3d5
Revises: b5e9c2f1a3d4
"""
from alembic import op
import sqlalchemy as sa

revision = "c7f2a1b9e3d5"
down_revision = "b5e9c2f1a3d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "stats_pages" in inspector.get_table_names():
        return

    op.create_table(
        "stats_pages",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("icon", sa.String(length=50), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("layout", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        # AuditMixin columns
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stats_pages_position", "stats_pages", ["position"])

    # Seed one empty starter page so /stats renders a tab immediately.
    # is_system=true → can't be deleted, but its layout stays editable.
    op.execute(
        sa.text(
            "INSERT INTO stats_pages (id, name, icon, position, layout, "
            "is_system, is_active, created_at, updated_at) "
            "VALUES (:id, :name, :icon, 0, '[]', true, true, now(), now())"
        ).bindparams(
            id="sys-stats-overview",
            name="Overview",
            icon="LayoutDashboard",
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "stats_pages" not in inspector.get_table_names():
        return
    op.drop_index("ix_stats_pages_position", table_name="stats_pages")
    op.drop_table("stats_pages")
