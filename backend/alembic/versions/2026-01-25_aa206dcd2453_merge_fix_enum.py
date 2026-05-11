"""merge_fix_enum

Revision ID: aa206dcd2453
Revises: 024e34cc0fd1, fix_resource_type_enum
Create Date: 2026-01-25 06:41:57.450479+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'aa206dcd2453'
down_revision: Union[str, None] = ('024e34cc0fd1', 'fix_resource_type_enum')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
