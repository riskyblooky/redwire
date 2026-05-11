"""Add references + ATT&CK technique IDs to finding/testcase templates

- finding_templates: new `references` (Text, nullable) and
  `attack_technique_ids` (JSON, NOT NULL default '[]')
- testcase_templates: new `attack_technique_ids` (same shape)

Revision ID: d9e0f1g2h3i4
Revises: c8d9e0f1g2h3
Create Date: 2026-05-08
"""
from alembic import op
import sqlalchemy as sa


revision = 'd9e0f1g2h3i4'
down_revision = 'c8d9e0f1g2h3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('finding_templates', sa.Column('references', sa.Text(), nullable=True))
    op.add_column(
        'finding_templates',
        sa.Column('attack_technique_ids', sa.JSON(), nullable=False, server_default='[]'),
    )
    op.add_column(
        'testcase_templates',
        sa.Column('attack_technique_ids', sa.JSON(), nullable=False, server_default='[]'),
    )


def downgrade() -> None:
    op.drop_column('testcase_templates', 'attack_technique_ids')
    op.drop_column('finding_templates', 'attack_technique_ids')
    op.drop_column('finding_templates', 'references')
