"""add infrastructure tables

Revision ID: m3n4o5p6q7r8
Revises: l2m3n4o5p6q7
Create Date: 2026-03-14 03:44:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'm3n4o5p6q7r8'
down_revision: Union[str, None] = 'l2m3n4o5p6q7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Infra items table
    op.create_table('infra_items',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('infra_type', sa.String(length=20), server_default='OTHER', nullable=False),
        sa.Column('status', sa.String(length=20), server_default='ACTIVE', nullable=False),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('internal_ip', sa.String(length=45), nullable=True),
        sa.Column('hostname', sa.String(length=255), nullable=True),
        sa.Column('provider', sa.String(length=100), nullable=True),
        sa.Column('region', sa.String(length=100), nullable=True),
        sa.Column('os', sa.String(length=100), nullable=True),
        sa.Column('point_of_presence', sa.String(length=255), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_infra_items_name', 'infra_items', ['name'])

    # Association tables
    op.create_table('infra_item_findings',
        sa.Column('infra_item_id', sa.String(), nullable=False),
        sa.Column('finding_id', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['infra_item_id'], ['infra_items.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['finding_id'], ['findings.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('infra_item_id', 'finding_id'),
    )

    op.create_table('infra_item_testcases',
        sa.Column('infra_item_id', sa.String(), nullable=False),
        sa.Column('testcase_id', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['infra_item_id'], ['infra_items.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['testcase_id'], ['testcases.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('infra_item_id', 'testcase_id'),
    )

    op.create_table('infra_item_notes',
        sa.Column('infra_item_id', sa.String(), nullable=False),
        sa.Column('note_id', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['infra_item_id'], ['infra_items.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['note_id'], ['notes.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('infra_item_id', 'note_id'),
    )


def downgrade() -> None:
    op.drop_table('infra_item_notes')
    op.drop_table('infra_item_testcases')
    op.drop_table('infra_item_findings')
    op.drop_index('ix_infra_items_name', table_name='infra_items')
    op.drop_table('infra_items')
