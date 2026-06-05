"""add_inline_portion_marks

Revision ID: e1c5b9a72f38
Revises: d8f3a1b6c40e
Create Date: 2026-06-04 22:15:00.000000+00:00

Adds marking_profiles.inline_portion_marks (nullable bool). When False the
report renders the page banner only (no inline title/finding/table/image
marks) — the typical TLP idiom. Seeds existing rows: TLP off, others on.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'e1c5b9a72f38'
down_revision: Union[str, None] = 'd8f3a1b6c40e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('marking_profiles', sa.Column('inline_portion_marks', sa.Boolean(), nullable=True))
    # Seed existing profiles: TLP is banner-only; IC/custom keep inline marks.
    op.execute("UPDATE marking_profiles SET inline_portion_marks = (scheme <> 'TLP_2_0')")


def downgrade() -> None:
    op.drop_column('marking_profiles', 'inline_portion_marks')
