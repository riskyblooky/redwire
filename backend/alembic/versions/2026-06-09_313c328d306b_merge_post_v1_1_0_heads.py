"""merge_post_v1_1_0_heads

Revision ID: 313c328d306b
Revises: 9152816461c1, a3f7d9c1b4e2
Create Date: 2026-06-09 04:16:18.205100+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '313c328d306b'
down_revision: Union[str, None] = ('9152816461c1', 'a3f7d9c1b4e2')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
