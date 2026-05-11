"""add testcase_tags table

Revision ID: a2b3c4d5e6f8
Revises: b2c3d4e5f6g8
Create Date: 2026-02-12

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a2b3c4d5e6f8'
down_revision = 'b2c3d4e5f6g8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'testcase_tags',
        sa.Column('testcase_id', sa.String(), sa.ForeignKey('testcases.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('tag_id', sa.String(), sa.ForeignKey('tags.id', ondelete='CASCADE'), primary_key=True),
    )


def downgrade() -> None:
    op.drop_table('testcase_tags')
