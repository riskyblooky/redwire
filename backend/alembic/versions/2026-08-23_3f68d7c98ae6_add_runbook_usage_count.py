"""add runbook usage_count

Revision ID: 3f68d7c98ae6
Revises: 0da069add646
Create Date: 2026-08-23 23:52:54.540992+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3f68d7c98ae6'
down_revision: Union[str, None] = '0da069add646'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add a usage counter to runbooks (incremented when a runbook is applied to
    # an engagement). server_default='0' keeps the add safe on populated tables.
    # Unrelated index drift autogenerate picked up is intentionally excluded.
    op.add_column('runbooks', sa.Column('usage_count', sa.Integer(), server_default='0', nullable=False))


def downgrade() -> None:
    op.drop_column('runbooks', 'usage_count')
