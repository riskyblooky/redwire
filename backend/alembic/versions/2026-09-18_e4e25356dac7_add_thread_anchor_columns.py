"""add thread anchor columns

Revision ID: e4e25356dac7
Revises: f996904ad75d
Create Date: 2026-09-18 17:40:06.357604+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e4e25356dac7'
down_revision: Union[str, None] = 'f996904ad75d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Anchored peer-review comments (docs/anchored-comments-peer-review.md).
    # All nullable — legacy threads keep NULL and are treated as non-anchored.
    op.add_column('threads', sa.Column('anchor_field', sa.String(length=64), nullable=True))
    op.add_column('threads', sa.Column('anchor_quote', sa.Text(), nullable=True))
    op.add_column('threads', sa.Column('anchor_prefix', sa.String(length=128), nullable=True))
    op.add_column('threads', sa.Column('anchor_suffix', sa.String(length=128), nullable=True))
    op.add_column('threads', sa.Column('anchor_occurrence', sa.Integer(), nullable=True))
    op.add_column('threads', sa.Column('anchor_status', sa.String(length=16), nullable=True))
    # (autogenerate also flagged unrelated pre-existing index drift — omitted.)


def downgrade() -> None:
    op.drop_column('threads', 'anchor_status')
    op.drop_column('threads', 'anchor_occurrence')
    op.drop_column('threads', 'anchor_suffix')
    op.drop_column('threads', 'anchor_prefix')
    op.drop_column('threads', 'anchor_quote')
    op.drop_column('threads', 'anchor_field')
