"""add_logo_scale

Revision ID: f5b21d9c7e83
Revises: e1c5b9a72f38
Create Date: 2026-06-04 23:00:00.000000+00:00

Adds report_themes.logo_scale (nullable int percent). The cover logo now
preserves aspect ratio (bound to a base height); logo_scale scales that height.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'f5b21d9c7e83'
down_revision: Union[str, None] = 'e1c5b9a72f38'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('report_themes', sa.Column('logo_scale', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('report_themes', 'logo_scale')
