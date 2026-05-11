"""add note link tables

Revision ID: a1b2c3d4e5f7
Revises: c4d5e6f7g8h9
Create Date: 2026-02-10 19:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f7'
down_revision: Union[str, None] = 'c4d5e6f7g8h9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'note_assets',
        sa.Column('note_id', sa.String(), sa.ForeignKey('notes.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('asset_id', sa.String(), sa.ForeignKey('assets.id', ondelete='CASCADE'), primary_key=True),
    )

    op.create_table(
        'note_testcases',
        sa.Column('note_id', sa.String(), sa.ForeignKey('notes.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('testcase_id', sa.String(), sa.ForeignKey('testcases.id', ondelete='CASCADE'), primary_key=True),
    )

    op.create_table(
        'note_findings',
        sa.Column('note_id', sa.String(), sa.ForeignKey('notes.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('finding_id', sa.String(), sa.ForeignKey('findings.id', ondelete='CASCADE'), primary_key=True),
    )

    op.create_table(
        'note_vault_items',
        sa.Column('note_id', sa.String(), sa.ForeignKey('notes.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('vault_item_id', sa.String(), sa.ForeignKey('vault_items.id', ondelete='CASCADE'), primary_key=True),
    )

    op.create_table(
        'note_cleanup_artifacts',
        sa.Column('note_id', sa.String(), sa.ForeignKey('notes.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('cleanup_artifact_id', sa.String(), sa.ForeignKey('cleanup_artifacts.id', ondelete='CASCADE'), primary_key=True),
    )


def downgrade() -> None:
    op.drop_table('note_cleanup_artifacts')
    op.drop_table('note_vault_items')
    op.drop_table('note_findings')
    op.drop_table('note_testcases')
    op.drop_table('note_assets')
