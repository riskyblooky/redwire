"""add runbooks and runbook_items tables

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-02-07

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'f6a7b8c9d0e1'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        'runbooks',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('name', sa.String(500), nullable=False, index=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column('created_by', sa.String(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('updated_by', sa.String(), sa.ForeignKey('users.id'), nullable=True),
    )
    op.create_table(
        'runbook_items',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('runbook_id', sa.String(), sa.ForeignKey('runbooks.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('template_id', sa.String(), sa.ForeignKey('testcase_templates.id', ondelete='CASCADE'), nullable=False),
        sa.Column('parent_id', sa.String(), sa.ForeignKey('runbook_items.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
    )

def downgrade():
    op.drop_table('runbook_items')
    op.drop_table('runbooks')
