"""spray_results.username varchar(255) -> text for EncryptedText

Revision ID: a7c2d9e1b34f
Revises: 14b2ea8f7a8d
Create Date: 2026-06-28 21:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a7c2d9e1b34f'
down_revision: Union[str, None] = '14b2ea8f7a8d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # GHSA-3r7j-7h5r-gxgx follow-up. SprayResult.username moved from a
    # plain String(255) to the new EncryptedText (Fernet at rest via
    # the column TypeDecorator). Fernet ciphertext grows ~140 chars for
    # a 50-char plaintext and can exceed 255 for longer usernames or
    # any future schema widening, so the underlying SQL type drops the
    # length cap and becomes TEXT.
    #
    # Postgres permits varchar(255) -> text in place with no data
    # rewrite (varchar is just text + a length-check constraint).
    op.alter_column(
        'spray_results',
        'username',
        existing_type=sa.String(length=255),
        type_=sa.Text(),
        existing_nullable=False,
    )


def downgrade() -> None:
    # Truncating to varchar(255) on a column carrying Fernet ciphertext
    # would corrupt rows whose encrypted username happens to exceed
    # the cap. Pin the same length but cast through text-to-varchar so
    # the rollback path errors loudly on any over-long row rather than
    # silently truncating.
    op.alter_column(
        'spray_results',
        'username',
        existing_type=sa.Text(),
        type_=sa.String(length=255),
        existing_nullable=False,
    )
