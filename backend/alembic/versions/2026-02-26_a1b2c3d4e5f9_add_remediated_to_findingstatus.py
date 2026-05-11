"""add REMEDIATED to findingstatus enum

Revision ID: a1b2c3d4e5f9
Revises: 8dbbee2919e4
Create Date: 2026-02-26 07:12:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f9'
down_revision: Union[str, None] = '8dbbee2919e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE findingstatus ADD VALUE IF NOT EXISTS 'REMEDIATED'")


def downgrade() -> None:
    # PostgreSQL doesn't support removing enum values; this is a no-op
    pass
