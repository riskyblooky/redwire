"""delete orphaned version_history rows

Deleting a finding, test case, asset, note or engagement never deleted
the entities' version history (polymorphic, no FK). The delete paths now
sweep it; this removes the rows already orphaned.

Revision ID: a8d3f6c2e9b1
Revises: f5c2d8a4e6b3
Create Date: 2026-11-21
"""
import sqlalchemy as sa
from alembic import op

revision = "a8d3f6c2e9b1"
down_revision = "f5c2d8a4e6b3"
branch_labels = None
depends_on = None

_TABLES = {"finding": "findings", "testcase": "testcases", "asset": "assets", "note": "notes"}


def upgrade() -> None:
    for entity_type, table in _TABLES.items():
        # Table name from the constant map above; the type is bound.
        op.get_bind().execute(sa.text(
            "DELETE FROM version_history vh WHERE vh.entity_type = :t "
            f"AND NOT EXISTS (SELECT 1 FROM {table} x WHERE x.id = vh.entity_id)"  # noqa: S608
        ), {"t": entity_type})


def downgrade() -> None:
    # The deleted rows described entities that no longer exist.
    pass
