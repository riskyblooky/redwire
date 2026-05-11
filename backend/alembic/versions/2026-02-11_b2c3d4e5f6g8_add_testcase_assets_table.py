"""add testcase_assets association table

Revision ID: b2c3d4e5f6g8
Revises: a1b2c3d4e5f7
Create Date: 2026-02-11 00:50:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6g8'
down_revision: Union[str, None] = 'a1b2c3d4e5f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'testcase_assets',
        sa.Column('testcase_id', sa.String(), sa.ForeignKey('testcases.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('asset_id', sa.String(), sa.ForeignKey('assets.id', ondelete='CASCADE'), primary_key=True),
    )


def downgrade() -> None:
    op.drop_table('testcase_assets')
