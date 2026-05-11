"""add runbook_type column

Revision ID: a1b2c3d4e5g1
Revises: b2c634de918a
Create Date: 2026-04-10 05:09:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5g1'
down_revision: Union[str, None] = 'b2c634de918a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('runbooks', sa.Column('runbook_type', sa.String(100), nullable=True))
    op.create_index('ix_runbooks_runbook_type', 'runbooks', ['runbook_type'])


def downgrade() -> None:
    op.drop_index('ix_runbooks_runbook_type', 'runbooks')
    op.drop_column('runbooks', 'runbook_type')
