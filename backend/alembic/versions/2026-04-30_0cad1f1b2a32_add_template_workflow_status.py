"""add_template_workflow_status

Revision ID: 0cad1f1b2a32
Revises: s0t1u2v3w4x5
Create Date: 2026-04-30 22:32:40.672174+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0cad1f1b2a32'
down_revision: Union[str, None] = 's0t1u2v3w4x5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create the enum type explicitly so we control the value casing.
    template_status = sa.Enum('DRAFT', 'SUBMITTED', 'PUBLISHED', name='templatestatus')
    template_status.create(op.get_bind(), checkfirst=True)

    # Existing rows are PUBLISHED so they remain visible after the migration.
    op.add_column(
        'finding_templates',
        sa.Column('status', template_status, server_default='PUBLISHED', nullable=False),
    )
    op.add_column('finding_templates', sa.Column('submitted_at', sa.DateTime(), nullable=True))
    op.add_column('finding_templates', sa.Column('published_at', sa.DateTime(), nullable=True))
    op.add_column('finding_templates', sa.Column('published_by', sa.String(), nullable=True))
    op.add_column('finding_templates', sa.Column('review_note', sa.Text(), nullable=True))

    op.create_index(
        op.f('ix_finding_templates_status'),
        'finding_templates',
        ['status'],
        unique=False,
    )
    op.create_foreign_key(
        'fk_finding_templates_published_by_users',
        'finding_templates',
        'users',
        ['published_by'],
        ['id'],
    )


def downgrade() -> None:
    op.drop_constraint('fk_finding_templates_published_by_users', 'finding_templates', type_='foreignkey')
    op.drop_index(op.f('ix_finding_templates_status'), table_name='finding_templates')
    op.drop_column('finding_templates', 'review_note')
    op.drop_column('finding_templates', 'published_by')
    op.drop_column('finding_templates', 'published_at')
    op.drop_column('finding_templates', 'submitted_at')
    op.drop_column('finding_templates', 'status')

    sa.Enum(name='templatestatus').drop(op.get_bind(), checkfirst=True)
