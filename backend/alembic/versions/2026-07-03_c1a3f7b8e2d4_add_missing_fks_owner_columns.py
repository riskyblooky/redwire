"""add missing FKs on owner-shaped columns; purge orphans first

Revision ID: c1a3f7b8e2d4
Revises: 199be698dd4a
Create Date: 2026-07-03 12:00:00.000000+00:00

GHSA-jw3p-gjp8-2cf3 follow-up. That fix added a missing FK on
``infra_vault_items.infra_item_id``. A grep of the models turned up
four more columns of the same shape — named like foreign keys, used
like foreign keys, but declared as a bare ``Column(String, ...)``
with no ``ForeignKey`` constraint at the DB layer:

  * wordlist_entries.source              → wordlist_meta.id
  * infra_items.created_by               → users.id
  * ai_settings.updated_by               → users.id
  * auth_settings.updated_by             → users.id

Each has the same failure mode: deleting the parent row leaves dangling
values in the child table that no query notices (they just resolve to
nothing on join). Not a security hole today — every route that reads
the parent-id column authenticates on the parent existence too — but a
real data-integrity smell.

Upgrade order matters. Each ``CREATE ... FOREIGN KEY ...`` refuses to
run on a table with existing values that violate the new constraint.
Purge the offending values first (DELETE for the CASCADE case,
UPDATE ... = NULL for the SET NULL cases) so the DDL succeeds without
manual intervention. Purge counts are logged via ``RAISE NOTICE`` so
an operator running ``alembic upgrade heads`` sees exactly what got
dropped for forensic reasons.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c1a3f7b8e2d4"
down_revision: Union[str, None] = "199be698dd4a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. Purge / null orphans ─────────────────────────────────────
    # wordlist_entries.source — CASCADE semantics on FK, so orphan
    # rows must be DELETED (they have no valid parent to point at).
    op.execute("""
        DO $$
        DECLARE
            n_deleted INTEGER;
        BEGIN
            DELETE FROM wordlist_entries
            WHERE source IS NOT NULL
              AND source NOT IN (SELECT id FROM wordlist_meta);
            GET DIAGNOSTICS n_deleted = ROW_COUNT;
            IF n_deleted > 0 THEN
                RAISE NOTICE '[migrate:c1a3f7b8e2d4] purged % orphan wordlist_entries rows', n_deleted;
            END IF;
        END
        $$;
    """)

    # infra_items.created_by — SET NULL semantics on FK, so orphan
    # values just get nulled (the item survives the operator leaving,
    # attribution becomes anonymous).
    op.execute("""
        DO $$
        DECLARE
            n_nulled INTEGER;
        BEGIN
            UPDATE infra_items
            SET created_by = NULL
            WHERE created_by IS NOT NULL
              AND created_by NOT IN (SELECT id FROM users);
            GET DIAGNOSTICS n_nulled = ROW_COUNT;
            IF n_nulled > 0 THEN
                RAISE NOTICE '[migrate:c1a3f7b8e2d4] nulled % orphan infra_items.created_by refs', n_nulled;
            END IF;
        END
        $$;
    """)

    # ai_settings.updated_by — SET NULL semantics
    op.execute("""
        DO $$
        DECLARE
            n_nulled INTEGER;
        BEGIN
            UPDATE ai_settings
            SET updated_by = NULL
            WHERE updated_by IS NOT NULL
              AND updated_by NOT IN (SELECT id FROM users);
            GET DIAGNOSTICS n_nulled = ROW_COUNT;
            IF n_nulled > 0 THEN
                RAISE NOTICE '[migrate:c1a3f7b8e2d4] nulled % orphan ai_settings.updated_by refs', n_nulled;
            END IF;
        END
        $$;
    """)

    # auth_settings.updated_by — SET NULL semantics
    op.execute("""
        DO $$
        DECLARE
            n_nulled INTEGER;
        BEGIN
            UPDATE auth_settings
            SET updated_by = NULL
            WHERE updated_by IS NOT NULL
              AND updated_by NOT IN (SELECT id FROM users);
            GET DIAGNOSTICS n_nulled = ROW_COUNT;
            IF n_nulled > 0 THEN
                RAISE NOTICE '[migrate:c1a3f7b8e2d4] nulled % orphan auth_settings.updated_by refs', n_nulled;
            END IF;
        END
        $$;
    """)

    # ── 2. Add the FK constraints ──────────────────────────────────
    op.create_foreign_key(
        "fk_wordlist_entries_source_wordlist_meta",
        "wordlist_entries", "wordlist_meta",
        ["source"], ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_infra_items_created_by_users",
        "infra_items", "users",
        ["created_by"], ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_ai_settings_updated_by_users",
        "ai_settings", "users",
        ["updated_by"], ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_auth_settings_updated_by_users",
        "auth_settings", "users",
        ["updated_by"], ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_auth_settings_updated_by_users", "auth_settings", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_ai_settings_updated_by_users", "ai_settings", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_infra_items_created_by_users", "infra_items", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_wordlist_entries_source_wordlist_meta", "wordlist_entries", type_="foreignkey"
    )
