"""Add workflow status columns to testcase_templates and runbooks.

Reuses the existing `templatestatus` enum created by 0cad1f1b2a32.
Existing rows are backfilled to PUBLISHED so they remain visible.

Revision ID: c9742081543e
Revises: 0cad1f1b2a32
Create Date: 2026-04-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c9742081543e'
down_revision: Union[str, None] = '0cad1f1b2a32'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Reuse the existing enum type — do not create or drop it here.
TEMPLATE_STATUS = sa.Enum('DRAFT', 'SUBMITTED', 'PUBLISHED', name='templatestatus', create_type=False)


def _add_workflow_columns(table: str) -> None:
    op.add_column(
        table,
        sa.Column('status', TEMPLATE_STATUS, server_default='PUBLISHED', nullable=False),
    )
    op.add_column(table, sa.Column('submitted_at', sa.DateTime(), nullable=True))
    op.add_column(table, sa.Column('published_at', sa.DateTime(), nullable=True))
    op.add_column(table, sa.Column('published_by', sa.String(), nullable=True))
    op.add_column(table, sa.Column('review_note', sa.Text(), nullable=True))
    op.create_index(op.f(f'ix_{table}_status'), table, ['status'], unique=False)
    op.create_foreign_key(
        f'fk_{table}_published_by_users',
        table,
        'users',
        ['published_by'],
        ['id'],
    )


def _drop_workflow_columns(table: str) -> None:
    op.drop_constraint(f'fk_{table}_published_by_users', table, type_='foreignkey')
    op.drop_index(op.f(f'ix_{table}_status'), table_name=table)
    op.drop_column(table, 'review_note')
    op.drop_column(table, 'published_by')
    op.drop_column(table, 'published_at')
    op.drop_column(table, 'submitted_at')
    op.drop_column(table, 'status')


def upgrade() -> None:
    _add_workflow_columns('testcase_templates')
    _add_workflow_columns('runbooks')


def downgrade() -> None:
    _drop_workflow_columns('runbooks')
    _drop_workflow_columns('testcase_templates')
