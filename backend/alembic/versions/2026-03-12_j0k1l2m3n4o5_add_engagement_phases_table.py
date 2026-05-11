"""add engagement_phases table

Revision ID: j0k1l2m3n4o5
Revises: i9j0k1l2m3n4
Create Date: 2026-03-12 23:30:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'j0k1l2m3n4o5'
down_revision: Union[str, None] = 'i9j0k1l2m3n4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('engagement_phases',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('engagement_id', sa.String(), nullable=False),
        sa.Column('phase_name', sa.String(length=50), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('planned_start', sa.DateTime(), nullable=True),
        sa.Column('planned_end', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['engagement_id'], ['engagements.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_engagement_phases_engagement_id', 'engagement_phases', ['engagement_id'])


def downgrade() -> None:
    op.drop_index('ix_engagement_phases_engagement_id', table_name='engagement_phases')
    op.drop_table('engagement_phases')
