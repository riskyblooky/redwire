"""add vault_item_findings and vault_item_testcases tables

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-02-07

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        'vault_item_findings',
        sa.Column('vault_item_id', sa.String(), sa.ForeignKey('vault_items.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('finding_id', sa.String(), sa.ForeignKey('findings.id', ondelete='CASCADE'), primary_key=True),
    )
    op.create_table(
        'vault_item_testcases',
        sa.Column('vault_item_id', sa.String(), sa.ForeignKey('vault_items.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('testcase_id', sa.String(), sa.ForeignKey('testcases.id', ondelete='CASCADE'), primary_key=True),
    )

def downgrade():
    op.drop_table('vault_item_testcases')
    op.drop_table('vault_item_findings')
