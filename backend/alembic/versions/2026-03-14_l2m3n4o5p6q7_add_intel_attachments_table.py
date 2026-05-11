"""add intel attachments table

Revision ID: l2m3n4o5p6q7
Revises: k1l2m3n4o5p6
Create Date: 2026-03-13 22:08:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'l2m3n4o5p6q7'
down_revision: Union[str, None] = 'k1l2m3n4o5p6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('intel_attachments',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('intel_item_id', sa.String(), nullable=False),
        sa.Column('filename', sa.String(length=500), nullable=False),
        sa.Column('original_filename', sa.String(length=255), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=False),
        sa.Column('mime_type', sa.String(length=100), nullable=True),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['intel_item_id'], ['intel_items.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_intel_attachments_intel_item_id', 'intel_attachments', ['intel_item_id'])


def downgrade() -> None:
    op.drop_index('ix_intel_attachments_intel_item_id', table_name='intel_attachments')
    op.drop_table('intel_attachments')
