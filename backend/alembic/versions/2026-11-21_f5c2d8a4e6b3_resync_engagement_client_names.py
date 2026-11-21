"""Resync engagements' copy of their client's name.

Renaming a client didn't update ``engagements.client_name``, so
engagements of a renamed client still show (and search, report and
chart under) the old name. Copy the current name across once; the
client update endpoint keeps it in step from now on.

Revision ID: f5c2d8a4e6b3
Revises: e7a3c1f9b2d4
Create Date: 2026-11-21
"""
from alembic import op
import sqlalchemy as sa

revision = "f5c2d8a4e6b3"
down_revision = "e7a3c1f9b2d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text(
        "UPDATE engagements e SET client_name = c.name FROM clients c "
        "WHERE e.client_id = c.id AND e.client_name IS DISTINCT FROM c.name"
    ))


def downgrade() -> None:
    pass  # the old names aren't kept; nothing to restore
