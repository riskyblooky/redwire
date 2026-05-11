"""add theme_palette to users

Revision ID: 235908378ab5
Revises: t1u2v3w4x5y6
Create Date: 2026-05-03 17:38:31.920686+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '235908378ab5'
down_revision: Union[str, None] = 't1u2v3w4x5y6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column('theme_palette', sa.String(length=32), server_default='aurora', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('users', 'theme_palette')
