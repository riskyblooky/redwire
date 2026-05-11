"""Add testcase_attack_techniques M2M table

Mirrors the finding_attack_techniques table — same string-based
technique_id convention (resolved client-side from the static ATT&CK
dataset).

Revision ID: b7c8d9e0f1g2
Revises: a6b7c8d9e0f1
Create Date: 2026-05-06
"""
from alembic import op
import sqlalchemy as sa


revision = 'b7c8d9e0f1g2'
down_revision = 'a6b7c8d9e0f1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'testcase_attack_techniques',
        sa.Column('testcase_id', sa.String(), sa.ForeignKey('testcases.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('technique_id', sa.String(20), primary_key=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index(
        'ix_testcase_attack_techniques_technique',
        'testcase_attack_techniques',
        ['technique_id'],
    )


def downgrade() -> None:
    op.drop_index('ix_testcase_attack_techniques_technique', table_name='testcase_attack_techniques')
    op.drop_table('testcase_attack_techniques')
