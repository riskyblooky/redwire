"""repair the LDAP user created with email "[]"

LDAP JIT provisioning stored "[]" as the email of a directory user with no
mail attribute (email is unique, so at most one such row). Give it the
<username>@ldap.local fallback the login route intended, unless that's
taken.

Revision ID: d7b2e5f8a3c9
Revises: c4f1a7e3b8d2
Create Date: 2026-11-21
"""
import sqlalchemy as sa
from alembic import op

revision = "d7b2e5f8a3c9"
down_revision = "c4f1a7e3b8d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().execute(sa.text(
        "UPDATE users u SET email = u.username || '@ldap.local' "
        "WHERE u.email = '[]' AND u.auth_provider = 'ldap' "
        "AND NOT EXISTS (SELECT 1 FROM users o WHERE o.email = u.username || '@ldap.local')"
    ))


def downgrade() -> None:
    pass
