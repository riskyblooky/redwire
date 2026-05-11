"""Add spray campaigns and results tables

Revision ID: o6p7q8r9s0t1
Revises: a1b2c3d4e5g1
Create Date: 2026-04-26
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic
revision = 'o6p7q8r9s0t1'
down_revision = 'a1b2c3d4e5g1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Spray campaigns table
    op.create_table(
        'spray_campaigns',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('engagement_id', sa.String(), sa.ForeignKey('engagements.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('protocol', sa.String(20), nullable=True),
        sa.Column('target_host', sa.String(255), nullable=True),
        sa.Column('target_port', sa.Integer(), nullable=True),
        sa.Column('target_hostname', sa.String(255), nullable=True),
        sa.Column('domain', sa.String(255), nullable=True),
        sa.Column('password_used', sa.Text(), nullable=True),
        sa.Column('total_attempts', sa.Integer(), server_default='0'),
        sa.Column('successful', sa.Integer(), server_default='0'),
        sa.Column('locked_out', sa.Integer(), server_default='0'),
        sa.Column('failed', sa.Integer(), server_default='0'),
        sa.Column('status', sa.String(50), server_default='imported'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('imported_from', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column('created_by', sa.String(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('updated_by', sa.String(), sa.ForeignKey('users.id'), nullable=True),
    )
    op.create_index('ix_spray_campaigns_engagement', 'spray_campaigns', ['engagement_id'])

    # Spray results table
    op.create_table(
        'spray_results',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('campaign_id', sa.String(), sa.ForeignKey('spray_campaigns.id', ondelete='CASCADE'), nullable=False),
        sa.Column('username', sa.String(255), nullable=False),
        sa.Column('domain', sa.String(255), nullable=True),
        sa.Column('result', sa.String(50), nullable=False),
        sa.Column('status_code', sa.String(255), nullable=True),
        sa.Column('is_admin', sa.Boolean(), server_default='false'),
        sa.Column('vault_item_id', sa.String(), sa.ForeignKey('vault_items.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_spray_results_campaign', 'spray_results', ['campaign_id'])
    op.create_index('ix_spray_results_result', 'spray_results', ['result'])


def downgrade() -> None:
    op.drop_index('ix_spray_results_result', table_name='spray_results')
    op.drop_index('ix_spray_results_campaign', table_name='spray_results')
    op.drop_table('spray_results')
    op.drop_index('ix_spray_campaigns_engagement', table_name='spray_campaigns')
    op.drop_table('spray_campaigns')
