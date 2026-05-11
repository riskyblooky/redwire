"""Add must_change_password to users

Revision ID: c3d4e5f6a7b1
Revises: b2c3d4e5f6a0
Create Date: 2026-03-01 06:33:00

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b1'
down_revision: Union[str, None] = 'b2c3d4e5f6a0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('must_change_password', sa.Boolean(), nullable=False, server_default='false'))
    # Flag admin users so they are forced to change password on first login
    op.execute("UPDATE users SET must_change_password = true WHERE username = 'admin'")


def downgrade() -> None:
    op.drop_column('users', 'must_change_password')
