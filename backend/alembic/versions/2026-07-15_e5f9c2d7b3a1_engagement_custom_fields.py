"""custom_fields JSON column on engagements

Extends the custom-fields feature to engagements (the 5th entity). Nullable
JSON, safe on a populated table.

Revision ID: e5f9c2d7b3a1
Revises: d4e8b1c6a9f2
"""
from alembic import op
import sqlalchemy as sa

revision = "e5f9c2d7b3a1"
down_revision = "d4e8b1c6a9f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("engagements")}
    if "custom_fields" not in cols:
        op.add_column("engagements", sa.Column("custom_fields", sa.JSON(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("engagements")}
    if "custom_fields" in cols:
        op.drop_column("engagements", "custom_fields")
