"""Add named layouts support to attack_graph_layouts

Revision ID: a4b5c6d7e8f9
Revises: 9d9b13ccdaea
Create Date: 2026-04-05

Changes:
- Add 'name' column (String, not null, default 'Default')
- Add 'is_active' column (Boolean, not null, default False)
- Migrate existing rows: set name='Default', is_active=True
"""
from alembic import op
import sqlalchemy as sa

revision = 'a4b5c6d7e8f9'
down_revision = '9d9b13ccdaea'
branch_labels = None
depends_on = None


def upgrade():
    # Add the new columns (nullable first so existing rows don't fail)
    op.add_column('attack_graph_layouts', sa.Column('name', sa.String(), nullable=True))
    op.add_column('attack_graph_layouts', sa.Column('is_active', sa.Boolean(), nullable=True))

    # Back-fill existing rows
    op.execute("UPDATE attack_graph_layouts SET name = 'Default', is_active = TRUE")

    # Now make them non-nullable
    op.alter_column('attack_graph_layouts', 'name', nullable=False)
    op.alter_column('attack_graph_layouts', 'is_active', nullable=False)

    # Drop the unique index SQLAlchemy created from unique=True on engagement_id,
    # then recreate as a plain (non-unique) index to allow multiple layouts per engagement.
    op.drop_index('ix_attack_graph_layouts_engagement_id', table_name='attack_graph_layouts')
    op.create_index('ix_attack_graph_layouts_engagement_id', 'attack_graph_layouts', ['engagement_id'])


def downgrade():
    op.drop_column('attack_graph_layouts', 'is_active')
    op.drop_column('attack_graph_layouts', 'name')
