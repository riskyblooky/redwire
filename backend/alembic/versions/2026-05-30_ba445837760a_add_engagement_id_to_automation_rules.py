"""add engagement_id to automation_rules

Revision ID: ba445837760a
Revises: 38e4edf95f73
Create Date: 2026-05-30 23:40:11.401162+00:00

GHSA-jvcx-44v2-gc9m: automation rules become engagement-scoped. NULL
engagement_id continues to mean "global rule" (admin / VIEW_ALL_ENGAGEMENTS
only, gated at the handler). Existing rows stay NULL after this migration —
they're effectively global rules that the operator can edit to scope later.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'ba445837760a'
down_revision: Union[str, None] = '38e4edf95f73'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'automation_rules',
        sa.Column('engagement_id', sa.String(), nullable=True),
    )
    op.create_index(
        op.f('ix_automation_rules_engagement_id'),
        'automation_rules',
        ['engagement_id'],
        unique=False,
    )
    op.create_foreign_key(
        'fk_automation_rules_engagement_id',
        'automation_rules', 'engagements',
        ['engagement_id'], ['id'],
        ondelete='CASCADE',
    )


def downgrade() -> None:
    op.drop_constraint('fk_automation_rules_engagement_id', 'automation_rules', type_='foreignkey')
    op.drop_index(op.f('ix_automation_rules_engagement_id'), table_name='automation_rules')
    op.drop_column('automation_rules', 'engagement_id')
