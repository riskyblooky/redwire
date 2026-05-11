"""add PROPOSED to engagementstatus enum

Revision ID: i9j0k1l2m3n4
Revises: 9ddd4065e88e
Create Date: 2026-03-12 23:10:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'i9j0k1l2m3n4'
down_revision: Union[str, None] = '9ddd4065e88e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE engagementstatus ADD VALUE IF NOT EXISTS 'PROPOSED'")


def downgrade() -> None:
    # PostgreSQL doesn't support removing enum values; this is a no-op
    pass
