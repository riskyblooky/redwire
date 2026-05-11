"""add_cleanup_artifacts_to_sectiontype_enum

Revision ID: c4d5e6f7g8h9
Revises: a2b3c4d5e6f7
Create Date: 2026-02-09 23:20:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c4d5e6f7g8h9'
down_revision: Union[str, None] = 'a2b3c4d5e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add 'cleanup_artifacts' to the existing 'sectiontype' PostgreSQL enum
    op.execute("ALTER TYPE sectiontype ADD VALUE IF NOT EXISTS 'cleanup_artifacts'")


def downgrade() -> None:
    # PostgreSQL does not support removing values from enums easily.
    # A full recreation would be needed, which is risky. Leaving as-is.
    pass
