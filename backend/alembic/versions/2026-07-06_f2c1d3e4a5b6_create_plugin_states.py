"""Create plugin_states table

`plugin_states` tracks each plugin's enabled/disabled state, overriding
its manifest default so an operator can toggle a plugin off without
editing plugin.yaml. The model was added when the plugin system landed
but never got its own Alembic migration — early dev DBs picked up the
table via ``Base.metadata.create_all`` (long gone) or hand-made SQL,
so any tree that only ran migrations hit
``relation "plugin_states" does not exist`` the first time an operator
clicked the enable/disable toggle in the admin plugins panel.

Guard on existence so this is safe to run against DBs that already
have the table.

Revision ID: f2c1d3e4a5b6
Revises: e8a2c4d5f9b7
"""
from alembic import op
import sqlalchemy as sa

revision = "f2c1d3e4a5b6"
down_revision = "e8a2c4d5f9b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "plugin_states" in inspector.get_table_names():
        return

    op.create_table(
        "plugin_states",
        sa.Column("plugin_id", sa.String(length=100), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("installed_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("plugin_id"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "plugin_states" not in inspector.get_table_names():
        return
    op.drop_table("plugin_states")
