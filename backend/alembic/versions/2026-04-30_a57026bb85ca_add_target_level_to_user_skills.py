"""Add target_level (growth focus) to user_skills.

Revision ID: a57026bb85ca
Revises: c9742081543e
Create Date: 2026-04-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a57026bb85ca'
down_revision: Union[str, None] = 'c9742081543e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('user_skills', sa.Column('target_level', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('user_skills', 'target_level')
