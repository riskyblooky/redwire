"""Add registration_code_id to users table

Revision ID: f6a7b8c9d0e4
Revises: e5f6a7b8c9d3
Create Date: 2026-03-06
"""
from alembic import op
import sqlalchemy as sa

revision = 'f6a7b8c9d0e4'
down_revision = 'e5f6a7b8c9d3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('registration_code_id', sa.String(), nullable=True))
    op.create_foreign_key(
        'fk_users_registration_code_id',
        'users', 'registration_codes',
        ['registration_code_id'], ['id'],
        ondelete='SET NULL'
    )
    op.create_index('ix_users_registration_code_id', 'users', ['registration_code_id'])


def downgrade() -> None:
    op.drop_index('ix_users_registration_code_id')
    op.drop_constraint('fk_users_registration_code_id', 'users', type_='foreignkey')
    op.drop_column('users', 'registration_code_id')
