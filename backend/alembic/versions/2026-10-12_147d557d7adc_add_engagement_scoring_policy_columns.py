"""add engagement scoring policy columns

Revision ID: 147d557d7adc
Revises: fba1df2a0ab7
Create Date: 2026-10-12 19:39:59.864905+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '147d557d7adc'
down_revision: Union[str, None] = 'fba1df2a0ab7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Per-engagement scoring policy. Both nullable (engagements table populated):
    #   allowed_score_models — JSON list of model ids (null ⇒ inherit site policy)
    #   default_score_model  — default model id for new findings (null ⇒ inherit)
    op.add_column("engagements", sa.Column("allowed_score_models", sa.JSON(), nullable=True))
    op.add_column("engagements", sa.Column("default_score_model", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("engagements", "default_score_model")
    op.drop_column("engagements", "allowed_score_models")
