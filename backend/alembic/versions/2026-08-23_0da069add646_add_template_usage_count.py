"""add template usage_count

Revision ID: 0da069add646
Revises: 3a4444e7981b
Create Date: 2026-08-23 16:46:02.607314+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0da069add646'
down_revision: Union[str, None] = '3a4444e7981b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add a usage counter to both template tables. server_default='0' keeps the
    # add safe on populated tables (existing rows backfill to 0). Unrelated
    # index drift that autogenerate picked up (engagement_tags, stats_pages) is
    # intentionally NOT included here.
    op.add_column('finding_templates', sa.Column('usage_count', sa.Integer(), server_default='0', nullable=False))
    op.add_column('testcase_templates', sa.Column('usage_count', sa.Integer(), server_default='0', nullable=False))


def downgrade() -> None:
    op.drop_column('testcase_templates', 'usage_count')
    op.drop_column('finding_templates', 'usage_count')
