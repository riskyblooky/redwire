"""Add finding_attack_techniques M2M table

Revision ID: p7q8r9s0t1u2
Revises: o6p7q8r9s0t1
Create Date: 2026-04-26
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic
revision = 'p7q8r9s0t1u2'
down_revision = 'o6p7q8r9s0t1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'finding_attack_techniques',
        sa.Column('finding_id', sa.String(), sa.ForeignKey('findings.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('technique_id', sa.String(20), primary_key=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index(
        'ix_finding_attack_techniques_technique',
        'finding_attack_techniques',
        ['technique_id']
    )


def downgrade() -> None:
    op.drop_index('ix_finding_attack_techniques_technique', table_name='finding_attack_techniques')
    op.drop_table('finding_attack_techniques')
