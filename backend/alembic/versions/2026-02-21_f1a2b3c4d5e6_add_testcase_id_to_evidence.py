"""add testcase_id to evidence

Revision ID: f1a2b3c4d5e6
Revises: e8f9a0b1c2d3
Create Date: 2026-02-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'e8f9a0b1c2d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('evidence', sa.Column('testcase_id', sa.String(), nullable=True))
    op.create_foreign_key(
        'fk_evidence_testcase_id',
        'evidence', 'testcases',
        ['testcase_id'], ['id']
    )
    op.create_index('ix_evidence_testcase_id', 'evidence', ['testcase_id'])


def downgrade() -> None:
    op.drop_index('ix_evidence_testcase_id', table_name='evidence')
    op.drop_constraint('fk_evidence_testcase_id', 'evidence', type_='foreignkey')
    op.drop_column('evidence', 'testcase_id')
