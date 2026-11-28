"""Add cleanup_artifact_assets table

Revision ID: 20260209030100
Revises: 20260208204144
Create Date: 2026-02-09 03:01:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260209030100'
down_revision: Union[str, None] = '9b4e0d08d58c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'cleanup_artifact_assets',
        sa.Column('cleanup_artifact_id', sa.String(), sa.ForeignKey('cleanup_artifacts.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('asset_id', sa.String(), sa.ForeignKey('assets.id', ondelete='CASCADE'), primary_key=True),
    )


def downgrade() -> None:
    op.drop_table('cleanup_artifact_assets')
