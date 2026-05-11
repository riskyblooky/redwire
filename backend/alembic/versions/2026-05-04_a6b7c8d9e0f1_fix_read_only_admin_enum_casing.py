"""fix read_only_admin enum casing

Revision ID: a6b7c8d9e0f1
Revises: 550e5a621584
Create Date: 2026-05-04

The earlier add_read_only_admin_role migration added the enum value as
lowercase 'read_only_admin', but the existing userrole enum convention
uses uppercase names ('ADMIN', 'TEAM_LEAD', 'OPERATOR', 'READ_ONLY')
because SQLAlchemy sends Python enum NAMES rather than values for
SQLEnum columns. This caused 500s when assigning the role:
    invalid input value for enum userrole: "READ_ONLY_ADMIN"

Rename the existing lowercase value to uppercase. Idempotent: skips
silently if the uppercase value already exists (e.g., on fresh deploys
where the initial schema baked in the correct casing).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a6b7c8d9e0f1'
down_revision: Union[str, None] = '550e5a621584'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    result = bind.execute(
        sa.text(
            "SELECT enumlabel FROM pg_enum JOIN pg_type ON pg_enum.enumtypid = pg_type.oid "
            "WHERE pg_type.typname = 'userrole'"
        )
    )
    values = {row[0] for row in result}
    if 'read_only_admin' in values and 'READ_ONLY_ADMIN' not in values:
        op.execute("ALTER TYPE userrole RENAME VALUE 'read_only_admin' TO 'READ_ONLY_ADMIN'")
    elif 'READ_ONLY_ADMIN' not in values:
        # Neither casing exists — add the uppercase value directly.
        op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'READ_ONLY_ADMIN'")


def downgrade() -> None:
    # PostgreSQL does not support renaming back without a recreate.
    pass
