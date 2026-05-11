"""add theme_accent_custom to users

Revision ID: 550e5a621584
Revises: 235908378ab5
Create Date: 2026-05-04 05:36:46.119596+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '550e5a621584'
down_revision: Union[str, None] = '235908378ab5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column('theme_accent_custom', sa.String(length=7), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('users', 'theme_accent_custom')
