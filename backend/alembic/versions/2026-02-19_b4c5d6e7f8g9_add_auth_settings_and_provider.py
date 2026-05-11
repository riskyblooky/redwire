"""Add auth_settings table and auth_provider column to users

Revision ID: b4c5d6e7f8g9
Revises: a3b4c5d6e7f8
Create Date: 2026-02-19
"""
from alembic import op
import sqlalchemy as sa

revision = 'b4c5d6e7f8g9'
down_revision = 'a3b4c5d6e7f8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create auth_settings table
    op.create_table(
        'auth_settings',
        sa.Column('key', sa.String(128), primary_key=True),
        sa.Column('value', sa.Text(), nullable=True),
        sa.Column('is_encrypted', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('updated_by', sa.String(), nullable=True),
    )

    # Add auth_provider to users
    op.add_column('users', sa.Column('auth_provider', sa.String(16), nullable=False, server_default='local'))


def downgrade() -> None:
    op.drop_column('users', 'auth_provider')
    op.drop_table('auth_settings')
