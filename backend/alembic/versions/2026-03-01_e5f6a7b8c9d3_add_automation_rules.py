"""Add automation_rules table

Revision ID: e5f6a7b8c9d3
Revises: d4e5f6a7b8c2
Create Date: 2026-03-01
"""
from alembic import op
import sqlalchemy as sa

revision = 'e5f6a7b8c9d3'
down_revision = 'd4e5f6a7b8c2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    if not conn.dialect.has_table(conn, 'automation_rules'):
        op.create_table(
            'automation_rules',
            sa.Column('id', sa.String(), nullable=False),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('trigger_type', sa.String(64), nullable=False),
            sa.Column('conditions', sa.JSON(), nullable=False, server_default='[]'),
            sa.Column('actions', sa.JSON(), nullable=False, server_default='[]'),
            sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('created_by', sa.String(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
            sa.Column('last_triggered_at', sa.DateTime(), nullable=True),
            sa.Column('trigger_count', sa.Integer(), nullable=False, server_default='0'),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='CASCADE'),
        )
        op.create_index('ix_automation_rules_trigger_type', 'automation_rules', ['trigger_type'])
        op.create_index('ix_automation_rules_is_enabled', 'automation_rules', ['is_enabled'])


def downgrade() -> None:
    op.drop_index('ix_automation_rules_is_enabled')
    op.drop_index('ix_automation_rules_trigger_type')
    op.drop_table('automation_rules')
