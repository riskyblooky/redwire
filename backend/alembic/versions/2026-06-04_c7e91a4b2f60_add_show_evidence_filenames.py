"""add_show_evidence_filenames

Revision ID: c7e91a4b2f60
Revises: b80ed9333c61
Create Date: 2026-06-04 19:30:00.000000+00:00

Adds report_themes.show_evidence_filenames (nullable bool) — toggle whether
evidence/screenshot filenames appear in captions. Hand-written, scoped.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c7e91a4b2f60'
down_revision: Union[str, None] = 'b80ed9333c61'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('report_themes', sa.Column('show_evidence_filenames', sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column('report_themes', 'show_evidence_filenames')
