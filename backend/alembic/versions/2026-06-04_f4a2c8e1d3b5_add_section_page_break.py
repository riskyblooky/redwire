"""add_section_page_break

Revision ID: f4a2c8e1d3b5
Revises: a1f2c3d4e5b6
Create Date: 2026-06-04 05:05:00.000000+00:00

Adds report_sections.page_break_before (nullable bool) — force a page break
before a section when rendering. Hand-written to stay scoped.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'f4a2c8e1d3b5'
down_revision: Union[str, None] = 'a1f2c3d4e5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('report_sections', sa.Column('page_break_before', sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column('report_sections', 'page_break_before')
