"""indexes on hot foreign keys

Revision ID: b8d4f0a2c6e1
Revises: a7c3e9f1d5b2
Create Date: 2026-11-09

engagement_id on the main per-engagement tables, evidence.finding_id /
testcase_id, comments.thread_id, and the reverse side of every link table
had no index (Postgres doesn't index FK columns automatically), so every
engagement page, list and cascade delete sequentially scanned them.
activity_logs gets (engagement_id, created_at) for the feeds instead of a
single-column index.

Built CONCURRENTLY (outside the migration transaction) so a large prod
table never blocks writes while its index builds. IF NOT EXISTS keeps a
re-run after an interrupted build safe; an interrupted CONCURRENTLY build
leaves an INVALID index, which is dropped and rebuilt.
"""
from alembic import op
import sqlalchemy as sa


revision = "b8d4f0a2c6e1"
down_revision = "a7c3e9f1d5b2"
branch_labels = None
depends_on = None


# (index name, table, columns)
_INDEXES = [
    ("ix_activity_logs_engagement_created", "activity_logs", ["engagement_id", "created_at"]),
    ("ix_activity_logs_user_id", "activity_logs", ["user_id"]),
    ("ix_api_tokens_user_id", "api_tokens", ["user_id"]),
    ("ix_assets_engagement_id", "assets", ["engagement_id"]),
    ("ix_cleanup_artifact_assets_asset_id", "cleanup_artifact_assets", ["asset_id"]),
    ("ix_cleanup_artifact_findings_finding_id", "cleanup_artifact_findings", ["finding_id"]),
    ("ix_cleanup_artifact_testcases_testcase_id", "cleanup_artifact_testcases", ["testcase_id"]),
    ("ix_client_user_access_user_id", "client_user_access", ["user_id"]),
    ("ix_comments_thread_id", "comments", ["thread_id"]),
    ("ix_engagement_assignments_engagement_id", "engagement_assignments", ["engagement_id"]),
    ("ix_evidence_engagement_id", "evidence", ["engagement_id"]),
    ("ix_evidence_finding_id", "evidence", ["finding_id"]),
    ("ix_evidence_testcase_id", "evidence", ["testcase_id"]),
    ("ix_finding_assets_asset_id", "finding_assets", ["asset_id"]),
    ("ix_finding_tags_tag_id", "finding_tags", ["tag_id"]),
    ("ix_finding_testcases_testcase_id", "finding_testcases", ["testcase_id"]),
    ("ix_findings_engagement_id", "findings", ["engagement_id"]),
    ("ix_infra_item_findings_finding_id", "infra_item_findings", ["finding_id"]),
    ("ix_infra_item_testcases_testcase_id", "infra_item_testcases", ["testcase_id"]),
    ("ix_infra_vault_access_user_id", "infra_vault_access", ["user_id"]),
    ("ix_intel_item_findings_finding_id", "intel_item_findings", ["finding_id"]),
    ("ix_intel_item_testcases_testcase_id", "intel_item_testcases", ["testcase_id"]),
    ("ix_note_assets_asset_id", "note_assets", ["asset_id"]),
    ("ix_note_findings_finding_id", "note_findings", ["finding_id"]),
    ("ix_note_testcases_testcase_id", "note_testcases", ["testcase_id"]),
    ("ix_notifications_engagement_id", "notifications", ["engagement_id"]),
    ("ix_spray_campaigns_engagement_id", "spray_campaigns", ["engagement_id"]),
    ("ix_testcase_assets_asset_id", "testcase_assets", ["asset_id"]),
    ("ix_testcase_tags_tag_id", "testcase_tags", ["tag_id"]),
    ("ix_testcases_engagement_id", "testcases", ["engagement_id"]),
    ("ix_threads_engagement_id", "threads", ["engagement_id"]),
    ("ix_vault_item_assets_asset_id", "vault_item_assets", ["asset_id"]),
    ("ix_vault_item_findings_finding_id", "vault_item_findings", ["finding_id"]),
    ("ix_vault_item_testcases_testcase_id", "vault_item_testcases", ["testcase_id"]),
    ("ix_vault_items_engagement_id", "vault_items", ["engagement_id"]),
]


def upgrade():
    bind = op.get_bind()
    with op.get_context().autocommit_block():
        for name, table, cols in _INDEXES:
            invalid = bind.execute(sa.text(
                "SELECT 1 FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
                "WHERE c.relname = :n AND NOT i.indisvalid"
            ), {"n": name}).scalar()
            if invalid:
                op.execute(f'DROP INDEX CONCURRENTLY IF EXISTS "{name}"')
            col_sql = ", ".join(f'"{c}"' for c in cols)
            op.execute(f'CREATE INDEX CONCURRENTLY IF NOT EXISTS "{name}" ON "{table}" ({col_sql})')


def downgrade():
    with op.get_context().autocommit_block():
        for name, _table, _cols in _INDEXES:
            op.execute(f'DROP INDEX CONCURRENTLY IF EXISTS "{name}"')
