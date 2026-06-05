"""relax activity_log engagement fk to nullable + ON DELETE SET NULL

Revision ID: 9152816461c1
Revises: f5b21d9c7e83
Create Date: 2026-06-05 00:00:00.000000+00:00

GHSA-9h56-fv6g-5x98 audit-trail preservation. Lets activity_log rows
outlive their parent engagement so an "engagement deleted by user X"
tombstone (and every prior action under the engagement) survives the
delete commit; orphaned rows are queryable via
``WHERE engagement_id IS NULL`` and their ``resource_id`` /
``resource_name`` / ``user_id`` / ``details`` columns keep the
forensic trail intact.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '9152816461c1'
down_revision: Union[str, None] = 'f5b21d9c7e83'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'activity_logs', 'engagement_id',
        existing_type=sa.String(),
        nullable=True,
    )
    op.drop_constraint('activity_logs_engagement_id_fkey', 'activity_logs', type_='foreignkey')
    op.create_foreign_key(
        'activity_logs_engagement_id_fkey',
        'activity_logs', 'engagements',
        ['engagement_id'], ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('activity_logs_engagement_id_fkey', 'activity_logs', type_='foreignkey')
    op.create_foreign_key(
        'activity_logs_engagement_id_fkey',
        'activity_logs', 'engagements',
        ['engagement_id'], ['id'],
    )
    op.alter_column(
        'activity_logs', 'engagement_id',
        existing_type=sa.String(),
        nullable=False,
    )
