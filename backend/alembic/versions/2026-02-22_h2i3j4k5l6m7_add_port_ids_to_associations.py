"""add port_ids to finding_assets and testcase_assets

Revision ID: h2i3j4k5l6m7
Revises: g1h2i3j4k5l6
Create Date: 2026-02-22

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'h2i3j4k5l6m7'
down_revision = 'g1h2i3j4k5l6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('finding_assets', sa.Column('port_ids', sa.Text(), nullable=True))
    op.add_column('testcase_assets', sa.Column('port_ids', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('testcase_assets', 'port_ids')
    op.drop_column('finding_assets', 'port_ids')
