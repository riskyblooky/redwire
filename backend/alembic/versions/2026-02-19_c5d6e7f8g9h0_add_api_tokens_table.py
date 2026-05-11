"""Create api_tokens table

Revision ID: c5d6e7f8g9h0
Revises: b4c5d6e7f8g9
Create Date: 2026-02-19
"""
from alembic import op
import sqlalchemy as sa

revision = 'c5d6e7f8g9h0'
down_revision = 'b4c5d6e7f8g9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'api_tokens',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('token_hash', sa.String(64), unique=True, nullable=False, index=True),
        sa.Column('token_prefix', sa.String(12), nullable=False),
        sa.Column('permission', sa.String(4), nullable=False, server_default='ro'),
        sa.Column('user_id', sa.String(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_by', sa.String(), sa.ForeignKey('users.id'), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('api_tokens')
