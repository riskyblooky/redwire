"""Add TOTP two-factor authentication fields to users table

Revision ID: a3b4c5d6e7f8
Revises: a2b3c4d5e6f8
Create Date: 2026-02-19
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a3b4c5d6e7f8'
down_revision = 'a2b3c4d5e6f8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('totp_secret', sa.String(64), nullable=True))
    op.add_column('users', sa.Column('totp_enabled', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('users', sa.Column('totp_verified_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'totp_verified_at')
    op.drop_column('users', 'totp_enabled')
    op.drop_column('users', 'totp_secret')
