"""add finding scoring columns

Revision ID: fba1df2a0ab7
Revises: e4e25356dac7
Create Date: 2026-10-12 03:22:53.978660+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fba1df2a0ab7'
down_revision: Union[str, None] = 'e4e25356dac7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Pluggable finding scoring. Both nullable (findings table is populated):
    #   score_model  — id of the ScoringModel that produced the current rating
    #                  (null ⇒ legacy/free-form, treated as "cvss31" for display).
    #   score_inputs — raw metric selections, so the calculator round-trips and
    #                  reports can show the breakdown.
    op.add_column("findings", sa.Column("score_model", sa.String(length=64), nullable=True))
    op.add_column("findings", sa.Column("score_inputs", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("findings", "score_inputs")
    op.drop_column("findings", "score_model")
