"""Vault encryption: widen username and password columns to Text

Revision ID: a1b2c3d4e5g0
Revises: q6r7s8t9u0v1
Create Date: 2026-03-26

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'a1b2c3d4e5g0'
down_revision = 'q6r7s8t9u0v1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Widen username and password to TEXT for Fernet ciphertext storage.
    # In PostgreSQL, VARCHAR → TEXT is a metadata-only change (no rewrite).
    op.alter_column('vault_items', 'username',
                    existing_type=sa.String(255),
                    type_=sa.Text(),
                    existing_nullable=True)
    op.alter_column('vault_items', 'password',
                    existing_type=sa.String(1000),
                    type_=sa.Text(),
                    existing_nullable=True)


def downgrade() -> None:
    op.alter_column('vault_items', 'username',
                    existing_type=sa.Text(),
                    type_=sa.String(255),
                    existing_nullable=True)
    op.alter_column('vault_items', 'password',
                    existing_type=sa.Text(),
                    type_=sa.String(1000),
                    existing_nullable=True)
