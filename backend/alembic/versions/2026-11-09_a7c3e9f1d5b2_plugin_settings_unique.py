"""plugin_settings: UNIQUE (plugin_id, key)

Revision ID: a7c3e9f1d5b2
Revises: f4b9d2e7a1c3
Create Date: 2026-11-09

The model's comment claimed (plugin_id, key) was unique but no constraint
existed, and every writer did select-then-insert, so concurrent saves
could create duplicates — after which every scalar_one_or_none() on that
key raised MultipleResultsFound. Keeps the most recently updated row of
any duplicate set, then adds the constraint the writers now upsert on.
"""
from alembic import op


revision = "a7c3e9f1d5b2"
down_revision = "f4b9d2e7a1c3"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        DELETE FROM plugin_settings p
        USING (
            SELECT id, row_number() OVER (
                PARTITION BY plugin_id, key ORDER BY updated_at DESC NULLS LAST, id
            ) AS rn
            FROM plugin_settings
        ) d
        WHERE p.id = d.id AND d.rn > 1
    """)
    op.create_unique_constraint("uq_plugin_settings_plugin_key", "plugin_settings", ["plugin_id", "key"])


def downgrade():
    op.drop_constraint("uq_plugin_settings_plugin_key", "plugin_settings", type_="unique")
