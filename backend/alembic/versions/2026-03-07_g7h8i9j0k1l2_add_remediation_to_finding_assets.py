"""Add remediation tracking to finding_assets

Revision ID: g7h8i9j0k1l2
Revises: f6a7b8c9d0e4
Create Date: 2026-03-07
"""
from alembic import op
import sqlalchemy as sa

revision = 'g7h8i9j0k1l2'
down_revision = 'f6a7b8c9d0e4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('finding_assets', sa.Column('remediated', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('finding_assets', sa.Column('remediated_at', sa.DateTime(), nullable=True))
    op.add_column('finding_assets', sa.Column('remediated_by', sa.String(), nullable=True))
    op.create_foreign_key(
        'fk_finding_assets_remediated_by',
        'finding_assets', 'users',
        ['remediated_by'], ['id'],
        ondelete='SET NULL'
    )
    # Backfill existing rows
    op.execute("UPDATE finding_assets SET remediated = false WHERE remediated IS NULL")
    op.alter_column('finding_assets', 'remediated', nullable=False)


def downgrade() -> None:
    op.drop_constraint('fk_finding_assets_remediated_by', 'finding_assets', type_='foreignkey')
    op.drop_column('finding_assets', 'remediated_by')
    op.drop_column('finding_assets', 'remediated_at')
    op.drop_column('finding_assets', 'remediated')
