"""add asset_ports table

Revision ID: g1h2i3j4k5l6
Revises: f1a2b3c4d5e6
Create Date: 2026-02-21

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'g1h2i3j4k5l6'
down_revision = 'f1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'asset_ports',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('asset_id', sa.String(), sa.ForeignKey('assets.id', ondelete='CASCADE'), nullable=False),
        sa.Column('port_number', sa.Integer(), nullable=False),
        sa.Column('protocol', sa.Enum('TCP', 'UDP', name='portprotocol'), nullable=False, server_default='TCP'),
        sa.Column('service_name', sa.String(255), nullable=True),
        sa.Column('state', sa.Enum('OPEN', 'CLOSED', 'FILTERED', name='portstate'), nullable=False, server_default='OPEN'),
        sa.Column('version', sa.String(500), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('asset_id', 'port_number', 'protocol', name='uq_asset_port_protocol'),
    )
    op.create_index('ix_asset_ports_asset_id', 'asset_ports', ['asset_id'])


def downgrade() -> None:
    op.drop_index('ix_asset_ports_asset_id', table_name='asset_ports')
    op.drop_table('asset_ports')
    # Clean up enums
    sa.Enum(name='portprotocol').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='portstate').drop(op.get_bind(), checkfirst=True)
