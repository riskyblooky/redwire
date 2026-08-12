"""add user last_seen_version

Revision ID: 3a4444e7981b
Revises: d293b92a8e4f
Create Date: 2026-08-12 03:57:50.224644+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3a4444e7981b'
down_revision: Union[str, None] = 'd293b92a8e4f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('last_seen_version', sa.String(length=20), nullable=True))
    # NOTE: autogenerate also proposed dropping ix_engagement_tags_tag_id and
    # ix_stats_pages_position — pre-existing model/DB drift unrelated to this
    # change. Deliberately omitted so this migration only adds last_seen_version.


def downgrade() -> None:
    op.drop_column('users', 'last_seen_version')
