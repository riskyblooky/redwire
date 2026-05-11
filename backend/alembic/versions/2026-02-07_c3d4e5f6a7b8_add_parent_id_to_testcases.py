"""add parent_id to testcases

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-02-07 23:39:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('testcases', sa.Column('parent_id', sa.String(), nullable=True))
    op.create_foreign_key(
        'fk_testcases_parent_id',
        'testcases', 'testcases',
        ['parent_id'], ['id'],
        ondelete='SET NULL'
    )
    op.create_index('ix_testcases_parent_id', 'testcases', ['parent_id'])


def downgrade() -> None:
    op.drop_index('ix_testcases_parent_id', table_name='testcases')
    op.drop_constraint('fk_testcases_parent_id', 'testcases', type_='foreignkey')
    op.drop_column('testcases', 'parent_id')
