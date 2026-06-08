"""infra_vault_items.infra_item_id → infra_items.id ON DELETE CASCADE

Revision ID: a3f7d9c1b4e2
Revises: f5b21d9c7e83
Create Date: 2026-06-08 22:45:00.000000+00:00

GHSA-jw3p-gjp8-2cf3: `infra_vault_items.infra_item_id` was declared as a
plain indexed string column with no `ForeignKey` constraint. A 6b82a0f
fix attempt assumed a DB cascade existed, but it did not — so every
`DELETE /infra/items/{id}` left the encrypted child credentials in
place. Worse, `GET /infra/items/{deleted_id}/vault` continued to
decrypt and return them indefinitely.

This migration:

  1. Counts and purges any rows whose `infra_item_id` no longer maps to
     a parent `infra_items.id` (historical orphans accumulated before
     the FK landed; the only correct semantic is to drop them — the
     parent is gone and they were never reachable from the UI).
  2. Adds the missing `ForeignKey(infra_items.id, ondelete=CASCADE)`
     constraint so future parent deletes drop the child rows
     automatically.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a3f7d9c1b4e2'
down_revision = 'f5b21d9c7e83'
branch_labels = None
depends_on = None


_FK_NAME = 'fk_infra_vault_items_infra_item_id'


def upgrade():
    conn = op.get_bind()

    # 1. Purge orphan rows that would otherwise prevent the FK from
    #    being added. Log the count for the audit trail.
    orphan_count = conn.execute(sa.text(
        "SELECT COUNT(*) FROM infra_vault_items "
        "WHERE infra_item_id NOT IN (SELECT id FROM infra_items)"
    )).scalar() or 0
    if orphan_count:
        print(f"  [GHSA-jw3p] purging {orphan_count} orphan infra_vault_items row(s)")
        conn.execute(sa.text(
            "DELETE FROM infra_vault_items "
            "WHERE infra_item_id NOT IN (SELECT id FROM infra_items)"
        ))

    # 2. Add the missing FK with ON DELETE CASCADE.
    op.create_foreign_key(
        _FK_NAME,
        'infra_vault_items', 'infra_items',
        ['infra_item_id'], ['id'],
        ondelete='CASCADE',
    )


def downgrade():
    # Drop the FK so the column reverts to a plain indexed string.
    # The orphan deletion in upgrade() is not reversible — those rows
    # were unreachable from the application and are gone for good.
    op.drop_constraint(_FK_NAME, 'infra_vault_items', type_='foreignkey')
