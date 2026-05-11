"""Add theme_preference (UI theme) to users.

Revision ID: 2681e34bbd5d
Revises: a57026bb85ca
Create Date: 2026-05-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '2681e34bbd5d'
down_revision: Union[str, None] = 'a57026bb85ca'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column('theme_preference', sa.String(length=32), server_default='purple', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('users', 'theme_preference')
