"""add intel_feed verify_tls

Revision ID: d293b92a8e4f
Revises: a05559c23e41
Create Date: 2026-08-12 03:20:03.709178+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd293b92a8e4f'
down_revision: Union[str, None] = 'a05559c23e41'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default=true backfills existing feed rows (NOT NULL); existing feeds
    # keep verifying TLS, which is the safe default.
    op.add_column(
        'intel_feeds',
        sa.Column('verify_tls', sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    # NOTE: autogenerate also proposed dropping ix_engagement_tags_tag_id and
    # ix_stats_pages_position — pre-existing model/DB drift unrelated to this
    # change. Deliberately omitted so this migration only adds verify_tls.


def downgrade() -> None:
    op.drop_column('intel_feeds', 'verify_tls')
