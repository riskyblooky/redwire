"""merge_heads

Revision ID: 024e34cc0fd1
Revises: 88a062fc30df, add_discussion_tables
Create Date: 2026-01-25 06:09:08.861745+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '024e34cc0fd1'
down_revision: Union[str, None] = ('88a062fc30df', 'add_discussion_tables')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
