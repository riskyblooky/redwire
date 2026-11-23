"""one asset per identifier per engagement (case- and space-insensitive)

Imports matched identifiers case-insensitively, spray case-sensitively and a
single create not at all, so an engagement could hold two rows for the same
host. Duplicates are merged into the oldest row of each group — links,
ports, spray results, asset threads and attack-graph edges move to it (a
link the keeper already has is dropped) — and a unique index on
(engagement_id, lower(btrim(identifier))) stops new ones.

Revision ID: d9e2b7c4a1f6
Revises: c5f1a8e3d7b4
Create Date: 2026-11-23
"""
from alembic import op
import sqlalchemy as sa

revision = "d9e2b7c4a1f6"
down_revision = "c5f1a8e3d7b4"
branch_labels = None
depends_on = None

INDEX = "uq_assets_engagement_identifier_ci"

# Each statement is literal (no SQL built from strings). _asset_dups maps
# every duplicate to its group's keeper.
_MERGE = [
    """
    CREATE TEMP TABLE _asset_dups ON COMMIT DROP AS
    SELECT id AS dup_id, keeper FROM (
        SELECT id, first_value(id) OVER (
            PARTITION BY engagement_id, lower(btrim(identifier))
            ORDER BY created_at NULLS LAST, id
        ) AS keeper
        FROM assets
    ) s
    WHERE id <> keeper
    """,
    # Link tables: move a link unless the keeper already has it, then drop the rest.
    """UPDATE finding_assets t SET asset_id = d.keeper FROM _asset_dups d
       WHERE t.asset_id = d.dup_id AND NOT EXISTS (
           SELECT 1 FROM finding_assets k WHERE k.asset_id = d.keeper AND k.finding_id = t.finding_id)""",
    "DELETE FROM finding_assets t USING _asset_dups d WHERE t.asset_id = d.dup_id",
    """UPDATE testcase_assets t SET asset_id = d.keeper FROM _asset_dups d
       WHERE t.asset_id = d.dup_id AND NOT EXISTS (
           SELECT 1 FROM testcase_assets k WHERE k.asset_id = d.keeper AND k.testcase_id = t.testcase_id)""",
    "DELETE FROM testcase_assets t USING _asset_dups d WHERE t.asset_id = d.dup_id",
    """UPDATE note_assets t SET asset_id = d.keeper FROM _asset_dups d
       WHERE t.asset_id = d.dup_id AND NOT EXISTS (
           SELECT 1 FROM note_assets k WHERE k.asset_id = d.keeper AND k.note_id = t.note_id)""",
    "DELETE FROM note_assets t USING _asset_dups d WHERE t.asset_id = d.dup_id",
    """UPDATE vault_item_assets t SET asset_id = d.keeper FROM _asset_dups d
       WHERE t.asset_id = d.dup_id AND NOT EXISTS (
           SELECT 1 FROM vault_item_assets k WHERE k.asset_id = d.keeper AND k.vault_item_id = t.vault_item_id)""",
    "DELETE FROM vault_item_assets t USING _asset_dups d WHERE t.asset_id = d.dup_id",
    """UPDATE cleanup_artifact_assets t SET asset_id = d.keeper FROM _asset_dups d
       WHERE t.asset_id = d.dup_id AND NOT EXISTS (
           SELECT 1 FROM cleanup_artifact_assets k
           WHERE k.asset_id = d.keeper AND k.cleanup_artifact_id = t.cleanup_artifact_id)""",
    "DELETE FROM cleanup_artifact_assets t USING _asset_dups d WHERE t.asset_id = d.dup_id",
    # Ports: unique per (asset, port, protocol).
    """UPDATE asset_ports t SET asset_id = d.keeper FROM _asset_dups d
       WHERE t.asset_id = d.dup_id AND NOT EXISTS (
           SELECT 1 FROM asset_ports k WHERE k.asset_id = d.keeper
             AND k.port_number = t.port_number AND k.protocol = t.protocol)""",
    "DELETE FROM asset_ports t USING _asset_dups d WHERE t.asset_id = d.dup_id",
    "UPDATE spray_results t SET asset_id = d.keeper FROM _asset_dups d WHERE t.asset_id = d.dup_id",
    # References without a foreign key.
    """UPDATE threads t SET resource_id = d.keeper FROM _asset_dups d
       WHERE lower(t.resource_type) = 'asset' AND t.resource_id = d.dup_id""",
    """UPDATE attacker_node_edges t SET target_node_id = 'asset-' || d.keeper FROM _asset_dups d
       WHERE t.target_node_id = 'asset-' || d.dup_id AND NOT EXISTS (
           SELECT 1 FROM attacker_node_edges k
           WHERE k.attacker_node_id = t.attacker_node_id AND k.target_node_id = 'asset-' || d.keeper)""",
    "DELETE FROM attacker_node_edges t USING _asset_dups d WHERE t.target_node_id = 'asset-' || d.dup_id",
    "DELETE FROM assets a USING _asset_dups d WHERE a.id = d.dup_id",
]


def upgrade():
    for stmt in _MERGE:
        op.execute(sa.text(stmt))
    op.create_index(INDEX, "assets", ["engagement_id", sa.text("lower(btrim(identifier))")], unique=True)


def downgrade():
    # Merged duplicates are not restored.
    op.drop_index(INDEX, table_name="assets")
