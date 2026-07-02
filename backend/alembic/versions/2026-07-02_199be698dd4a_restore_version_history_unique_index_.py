"""restore version_history unique index; dedupe first

Revision ID: 199be698dd4a
Revises: a7c2d9e1b34f
Create Date: 2026-07-02 05:21:56.003877+00:00

GHSA-7x2f-ff7r-h388 #12 (CWE-362) — restore the composite unique
index on (entity_type, entity_id, version) that Alembic revision
753bbc1309ea accidentally dropped when the VersionHistory model
didn't declare it in __table_args__. Since revision 753bbc1309ea,
concurrent writers to the same entity have been able to land
duplicate version rows because the versioning helper reads
MAX(version)+1 without any serialising lock.

Upgrade must **dedupe existing duplicates** before creating the
unique constraint — otherwise the DDL fails on any table where the
race actually happened. Keep the oldest row per (entity_type,
entity_id, version) tuple; drop the rest.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '199be698dd4a'
down_revision: Union[str, None] = 'a7c2d9e1b34f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. dedupe existing duplicates ─────────────────────────────
    # Keep the row with the earliest created_at per key. Ties
    # broken by id ascending so the same row is kept on repeated
    # runs (idempotency).
    op.execute("""
        DELETE FROM version_history
        WHERE id IN (
            SELECT id FROM (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY entity_type, entity_id, version
                           ORDER BY created_at ASC, id ASC
                       ) AS rn
                FROM version_history
            ) t
            WHERE rn > 1
        );
    """)

    # ── 2. add the unique constraint ─────────────────────────────
    op.create_unique_constraint(
        'uq_version_history_entity_version',
        'version_history',
        ['entity_type', 'entity_id', 'version'],
    )


def downgrade() -> None:
    op.drop_constraint(
        'uq_version_history_entity_version', 'version_history', type_='unique'
    )
