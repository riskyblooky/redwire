"""merge_named_layouts_and_note_parent

Revision ID: 67d550d27923
Revises: a4b5c6d7e8f9, add_note_parent_id
Create Date: 2026-04-06 04:21:19.667798+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '67d550d27923'
down_revision: Union[str, None] = ('a4b5c6d7e8f9', 'add_note_parent_id')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
