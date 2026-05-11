"""Add read_only_admin to userrole enum

Revision ID: t1u2v3w4x5y6
Revises: 2681e34bbd5d
Create Date: 2026-05-03

"""
from typing import Sequence, Union

from alembic import op


revision: str = 't1u2v3w4x5y6'
down_revision: Union[str, None] = '2681e34bbd5d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # IF NOT EXISTS makes this idempotent — safe on fresh deploys where
    # the initial schema already includes READ_ONLY_ADMIN in the enum.
    op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'read_only_admin'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values.
    # To fully roll back, you would need to recreate the type.
    pass
