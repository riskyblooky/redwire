"""marking_static_headings_and_card_style

Revision ID: d8f3a1b6c40e
Revises: c7e91a4b2f60
Create Date: 2026-06-04 20:30:00.000000+00:00

Adds:
  - marking_profiles.static_heading_marks (LOWEST | INHERIT)
  - report_themes.show_finding_severity_bar
  - report_themes.show_section_title_background
All nullable; the generator falls back to sensible defaults when null.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'd8f3a1b6c40e'
down_revision: Union[str, None] = 'c7e91a4b2f60'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('marking_profiles', sa.Column('static_heading_marks', sa.String(length=20), nullable=True))
    op.add_column('report_themes', sa.Column('show_finding_severity_bar', sa.Boolean(), nullable=True))
    op.add_column('report_themes', sa.Column('show_section_title_background', sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column('report_themes', 'show_section_title_background')
    op.drop_column('report_themes', 'show_finding_severity_bar')
    op.drop_column('marking_profiles', 'static_heading_marks')
