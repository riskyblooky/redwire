"""add_is_system_is_default_to_groups

Revision ID: a1b2c3d4f7g8
Revises: 664856e9c616
Create Date: 2026-02-08
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = 'a1b2c3d4f7g8'
down_revision = '664856e9c616'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [c['name'] for c in inspector.get_columns('groups')]

    # Add columns with server defaults so existing rows get False
    if 'is_system' not in columns:
        op.add_column('groups', sa.Column('is_system', sa.Boolean(), nullable=False, server_default='false'))
    if 'is_default' not in columns:
        op.add_column('groups', sa.Column('is_default', sa.Boolean(), nullable=False, server_default='false'))

    # Mark Administrators as system group
    op.execute("UPDATE groups SET is_system = true WHERE name = 'Administrators'")
    # Mark Default/Operators as system + default group
    op.execute("UPDATE groups SET is_system = true, is_default = true WHERE name IN ('Default', 'Operators')")


def downgrade() -> None:
    op.drop_column('groups', 'is_default')
    op.drop_column('groups', 'is_system')
