"""widen totp_secret for fernet encryption

Revision ID: d7e8f9a0b1c2
Revises: c5d6e7f8g9h0
Create Date: 2026-02-20
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "d7e8f9a0b1c2"
down_revision = "c5d6e7f8g9h0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "users",
        "totp_secret",
        existing_type=sa.String(64),
        type_=sa.String(256),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "users",
        "totp_secret",
        existing_type=sa.String(256),
        type_=sa.String(64),
        existing_nullable=True,
    )
