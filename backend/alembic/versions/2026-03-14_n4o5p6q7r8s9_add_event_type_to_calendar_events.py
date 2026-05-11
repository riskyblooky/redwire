"""add event_type to calendar_events

Revision ID: n4o5p6q7r8s9
Revises: m3n4o5p6q7r8
Create Date: 2026-03-14 05:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'n4o5p6q7r8s9'
down_revision: Union[str, None] = 'm3n4o5p6q7r8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('calendar_events', sa.Column('event_type', sa.String(length=20), server_default='EVENT', nullable=False))


def downgrade() -> None:
    op.drop_column('calendar_events', 'event_type')
