"""link spray_results to assets

Revision ID: s0t1u2v3w4x5
Revises: r9s0t1u2v3w4
Create Date: 2026-04-29

Adds an asset_id FK to spray_results so each per-host spray attempt can be
linked back to the engagement's asset inventory. Set on commit by matching
the result's target_host against asset.identifier; nullable so unmatched
results (or older rows) remain valid.
"""
from alembic import op
import sqlalchemy as sa


revision = 's0t1u2v3w4x5'
down_revision = 'r9s0t1u2v3w4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    cols = [c['name'] for c in inspector.get_columns('spray_results')]
    if 'asset_id' not in cols:
        op.add_column('spray_results', sa.Column('asset_id', sa.String(), nullable=True))
        op.create_foreign_key(
            'fk_spray_results_asset_id',
            'spray_results', 'assets',
            ['asset_id'], ['id'],
            ondelete='SET NULL',
        )
        op.create_index(
            'ix_spray_results_asset_id',
            'spray_results', ['asset_id'],
        )


def downgrade() -> None:
    op.drop_index('ix_spray_results_asset_id', table_name='spray_results')
    op.drop_constraint('fk_spray_results_asset_id', 'spray_results', type_='foreignkey')
    op.drop_column('spray_results', 'asset_id')
