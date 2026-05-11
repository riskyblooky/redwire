"""add ai_settings table

Revision ID: h8i9j0k1l2m3
Revises: g7h8i9j0k1l2
Create Date: 2026-03-07
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = 'h8i9j0k1l2m3'
down_revision = 'g7h8i9j0k1l2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'ai_settings',
        sa.Column('key', sa.String(128), primary_key=True),
        sa.Column('value', sa.Text, nullable=True),
        sa.Column('is_encrypted', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('updated_at', sa.DateTime, nullable=True),
        sa.Column('updated_by', sa.String, nullable=True),
    )


def downgrade() -> None:
    op.drop_table('ai_settings')
