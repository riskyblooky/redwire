"""add can_manage to infra_vault_access

Revision ID: 38e4edf95f73
Revises: d9e0f1g2h3i4
Create Date: 2026-05-18 06:38:48.465476+00:00

Per-grant marker on InfraVaultAccess for whether the grantee may
grant/revoke ACL rows on the item. Default False — only an explicit
True from an admin/team-lead delegates membership-management. Closes
the "every grantee is a granter" hole reported as GHSA-58q3-f33p-w84m.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '38e4edf95f73'
down_revision: Union[str, None] = 'd9e0f1g2h3i4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'infra_vault_access',
        sa.Column('can_manage', sa.Boolean(), server_default='false', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('infra_vault_access', 'can_manage')
