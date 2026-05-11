"""add parent_id to notes for tree hierarchy

Revision ID: add_note_parent_id
Revises: fix_resource_type_enum
Create Date: 2026-04-05 20:30:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_note_parent_id'
down_revision = '9d9b13ccdaea'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('notes', sa.Column('parent_id', sa.String(), nullable=True))
    op.create_index('ix_notes_parent_id', 'notes', ['parent_id'])
    op.create_foreign_key(
        'fk_notes_parent_id',
        'notes', 'notes',
        ['parent_id'], ['id'],
        ondelete='SET NULL'
    )


def downgrade():
    op.drop_constraint('fk_notes_parent_id', 'notes', type_='foreignkey')
    op.drop_index('ix_notes_parent_id', table_name='notes')
    op.drop_column('notes', 'parent_id')
