"""Add discussion and activity log tables

Revision ID: add_discussion_tables
Revises: 
Create Date: 2026-01-25 00:04:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_discussion_tables'
down_revision = 'ce0d66f1543c'  # Latest migration: add_asset_tracking_fields
branch_labels = None
depends_on = None


def upgrade():
    # Create threads table
    op.create_table(
        'threads',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('engagement_id', sa.String(), nullable=False),
        sa.Column('resource_type', sa.Enum('engagement', 'finding', 'asset', 'testcase', name='resourcetype'), nullable=False),
        sa.Column('resource_id', sa.String(), nullable=True),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('created_by', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('is_resolved', sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['engagement_id'], ['engagements.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_threads_resource_id'), 'threads', ['resource_id'], unique=False)

    # Create comments table
    op.create_table(
        'comments',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('thread_id', sa.String(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_by', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('is_resolvable', sa.Boolean(), nullable=True),
        sa.Column('is_resolved', sa.Boolean(), nullable=True),
        sa.Column('resolved_by', sa.String(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['resolved_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['thread_id'], ['threads.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create activity_logs table
    op.create_table(
        'activity_logs',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('engagement_id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('resource_type', sa.Enum('engagement', 'finding', 'asset', 'testcase', name='resourcetype'), nullable=False),
        sa.Column('resource_id', sa.String(), nullable=False),
        sa.Column('resource_name', sa.String(length=255), nullable=True),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['engagement_id'], ['engagements.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('activity_logs')
    op.drop_table('comments')
    op.drop_index(op.f('ix_threads_resource_id'), table_name='threads')
    op.drop_table('threads')
    # Drop the enum type
    sa.Enum(name='resourcetype').drop(op.get_bind(), checkfirst=True)
