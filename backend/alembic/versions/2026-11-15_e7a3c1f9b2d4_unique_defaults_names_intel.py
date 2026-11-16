"""Unique indexes for rows the code looks up as "the one": default group,
default report theme / marking profile, a layout's per-engagement default,
intel items per (feed, link), engagement names, attacker-node edges.

Each was check-then-insert with no constraint, so a race or a seeder could
create a second row, after which ``scalar_one_or_none()`` raised and the
endpoint 500'd (user creation once a renamed default group had been
re-seeded; a feed that stopped refreshing for good). Existing duplicates are
resolved first, keeping the row people most plausibly mean:

- default group: the one with the most members (a re-seeded copy is empty);
- default theme: a non-system theme over the seeded system one, then the
  most recently updated; marking profile / layout: most recently updated;
- intel items: the oldest; links and attachments move to it;
- engagement names: the oldest keeps its name, later ones get " (2)", " (3)"…
  Names are also trimmed;
- attacker edges: one of each pair (they carry nothing else).

Revision ID: e7a3c1f9b2d4
Revises: d4f1b7c3e9a2
Create Date: 2026-11-15
"""

import sqlalchemy as sa
from alembic import op

revision = "e7a3c1f9b2d4"
down_revision = "d4f1b7c3e9a2"
branch_labels = None
depends_on = None


def _keep_one_default(table: str, order_by: str, partition: str | None = None) -> None:
    part = f"PARTITION BY {partition} " if partition else ""
    op.execute(sa.text(f"""
        UPDATE {table} SET is_default = false
        WHERE id IN (
            SELECT id FROM (
                SELECT id, row_number() OVER ({part}ORDER BY {order_by}) AS rn
                FROM {table} WHERE is_default
            ) ranked WHERE rn > 1
        )
    """))


def upgrade() -> None:
    conn = op.get_bind()

    # ── Default flags ────────────────────────────────────────────────
    _keep_one_default(
        "groups",
        "(SELECT count(*) FROM user_groups ug WHERE ug.group_id = groups.id) DESC, id",
    )
    _keep_one_default("report_themes", "is_system ASC, updated_at DESC NULLS LAST, id")
    _keep_one_default("marking_profiles", "updated_at DESC NULLS LAST, id")
    _keep_one_default("report_layouts", "updated_at DESC NULLS LAST, id", partition="engagement_id")
    op.create_index("uq_groups_one_default", "groups", ["is_default"], unique=True,
                    postgresql_where=sa.text("is_default"))
    op.create_index("uq_report_themes_one_default", "report_themes", ["is_default"], unique=True,
                    postgresql_where=sa.text("is_default"))
    op.create_index("uq_marking_profiles_one_default", "marking_profiles", ["is_default"], unique=True,
                    postgresql_where=sa.text("is_default"))
    op.create_index("uq_report_layouts_one_default", "report_layouts", ["engagement_id"], unique=True,
                    postgresql_where=sa.text("is_default"))

    # ── Intel items: merge duplicates into the oldest ────────────────
    conn.execute(sa.text("""
        CREATE TEMP TABLE _intel_dupes AS
        SELECT id AS dup_id, keep_id FROM (
            SELECT id,
                   first_value(id) OVER w AS keep_id,
                   row_number() OVER w AS rn
            FROM intel_items
            WHERE feed_id IS NOT NULL AND source_url IS NOT NULL
            WINDOW w AS (PARTITION BY feed_id, source_url ORDER BY created_at, id)
        ) r WHERE rn > 1
    """))
    for table, col in (("intel_item_findings", "finding_id"),
                       ("intel_item_testcases", "testcase_id"),
                       ("intel_item_notes", "note_id")):
        conn.execute(sa.text(f"""
            INSERT INTO {table} (intel_item_id, {col})
            SELECT d.keep_id, t.{col} FROM {table} t JOIN _intel_dupes d ON t.intel_item_id = d.dup_id
            ON CONFLICT DO NOTHING
        """))
    conn.execute(sa.text("""
        UPDATE intel_attachments a SET intel_item_id = d.keep_id
        FROM _intel_dupes d WHERE a.intel_item_id = d.dup_id
    """))
    conn.execute(sa.text("DELETE FROM intel_items WHERE id IN (SELECT dup_id FROM _intel_dupes)"))
    conn.execute(sa.text("DROP TABLE _intel_dupes"))
    op.create_index("uq_intel_items_feed_source_url", "intel_items", ["feed_id", "source_url"], unique=True,
                    postgresql_where=sa.text("feed_id IS NOT NULL AND source_url IS NOT NULL"))

    # ── Engagement names ─────────────────────────────────────────────
    conn.execute(sa.text("UPDATE engagements SET name = btrim(name) WHERE name <> btrim(name)"))
    rows = conn.execute(sa.text("""
        SELECT id, name FROM engagements
        WHERE lower(name) IN (SELECT lower(name) FROM engagements GROUP BY lower(name) HAVING count(*) > 1)
        ORDER BY lower(name), created_at, id
    """)).fetchall()
    taken = {r[0].lower() for r in conn.execute(sa.text("SELECT lower(name) FROM engagements"))}
    seen: set[str] = set()
    for eng_id, name in rows:
        key = name.lower()
        if key not in seen:
            seen.add(key)  # the oldest keeps its name
            continue
        n, base = 2, name[:240]  # name is String(255)
        while f"{base} ({n})".lower() in taken:
            n += 1
        new = f"{base} ({n})"
        taken.add(new.lower())
        conn.execute(sa.text("UPDATE engagements SET name = :n WHERE id = :i"), {"n": new, "i": eng_id})
    op.create_index("uq_engagements_name_ci", "engagements", [sa.text("lower(btrim(name))")], unique=True)

    # ── Attacker-node edges ──────────────────────────────────────────
    conn.execute(sa.text("""
        DELETE FROM attacker_node_edges WHERE id IN (
            SELECT id FROM (
                SELECT id, row_number() OVER (PARTITION BY attacker_node_id, target_node_id
                                              ORDER BY id) AS rn
                FROM attacker_node_edges
            ) r WHERE rn > 1
        )
    """))
    op.create_unique_constraint("uq_attacker_node_edges_pair", "attacker_node_edges",
                                ["attacker_node_id", "target_node_id"])


def downgrade() -> None:
    op.drop_constraint("uq_attacker_node_edges_pair", "attacker_node_edges", type_="unique")
    op.drop_index("uq_engagements_name_ci", table_name="engagements")
    op.drop_index("uq_intel_items_feed_source_url", table_name="intel_items")
    op.drop_index("uq_report_layouts_one_default", table_name="report_layouts")
    op.drop_index("uq_marking_profiles_one_default", table_name="marking_profiles")
    op.drop_index("uq_report_themes_one_default", table_name="report_themes")
    op.drop_index("uq_groups_one_default", table_name="groups")
