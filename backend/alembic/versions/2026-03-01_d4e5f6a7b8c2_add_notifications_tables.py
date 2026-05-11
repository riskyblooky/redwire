"""Add notifications and notification_preferences tables

Revision ID: d4e5f6a7b8c2
Revises: c3d4e5f6a7b1
Create Date: 2026-03-01 19:44:00

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c2'
down_revision: Union[str, None] = 'c3d4e5f6a7b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Use raw SQL with IF NOT EXISTS for idempotency
    # (guards against partial applies from lock contention or manual creation)
    conn = op.get_bind()

    if not conn.dialect.has_table(conn, 'notifications'):
        op.create_table(
            'notifications',
            sa.Column('id', sa.String(), nullable=False),
            sa.Column('user_id', sa.String(), nullable=False),
            sa.Column('event_type', sa.String(64), nullable=False),
            sa.Column('title', sa.String(255), nullable=False),
            sa.Column('message', sa.Text(), nullable=True),
            sa.Column('link', sa.String(512), nullable=True),
            sa.Column('is_read', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('actor_id', sa.String(), nullable=True),
            sa.Column('engagement_id', sa.String(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['engagement_id'], ['engagements.id'], ondelete='SET NULL'),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('ix_notifications_user_id', 'notifications', ['user_id'])
        op.create_index('ix_notifications_event_type', 'notifications', ['event_type'])
        op.create_index('ix_notifications_created_at', 'notifications', ['created_at'])

    if not conn.dialect.has_table(conn, 'notification_preferences'):
        op.create_table(
            'notification_preferences',
            sa.Column('id', sa.String(), nullable=False),
            sa.Column('user_id', sa.String(), nullable=False),
            sa.Column('event_type', sa.String(64), nullable=False),
            sa.Column('site_muted', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('email_muted', sa.Boolean(), nullable=False, server_default='true'),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('user_id', 'event_type', name='uq_notification_pref_user_event'),
        )
        op.create_index('ix_notification_preferences_user_id', 'notification_preferences', ['user_id'])


def downgrade() -> None:
    op.drop_table('notification_preferences')
    op.drop_table('notifications')
