"""scope tags by entity type

Adds Tag.entity_type (finding / testcase / engagement) so tags are scoped per
entity type instead of one global pool. Existing tags are backfilled to the
entity type they're used with most (ties / unused → 'finding'), the old global
unique index on name is replaced with a composite unique on (name, entity_type).

Revision ID: a7c1e9d2b4f6
Revises: 3f68d7c98ae6
Create Date: 2026-08-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a7c1e9d2b4f6'
down_revision: Union[str, None] = '3f68d7c98ae6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add the column (server_default keeps the add safe on populated tables).
    op.add_column('tags', sa.Column('entity_type', sa.String(length=20), nullable=False, server_default='finding'))

    # 2. Backfill: assign each tag to the entity type it's associated with most.
    #    Tags with no associations (or ties) fall back to the 'finding' default.
    op.execute("""
        UPDATE tags t SET entity_type = x.et
        FROM (
            SELECT tag_id, et FROM (
                SELECT tag_id, et, cnt,
                       ROW_NUMBER() OVER (PARTITION BY tag_id ORDER BY cnt DESC, pri ASC) AS rn
                FROM (
                    SELECT tag_id, 'finding'    AS et, COUNT(*) AS cnt, 1 AS pri FROM finding_tags   GROUP BY tag_id
                    UNION ALL
                    SELECT tag_id, 'testcase'   AS et, COUNT(*) AS cnt, 2 AS pri FROM testcase_tags  GROUP BY tag_id
                    UNION ALL
                    SELECT tag_id, 'engagement' AS et, COUNT(*) AS cnt, 3 AS pri FROM engagement_tags GROUP BY tag_id
                ) counts
            ) ranked
            WHERE rn = 1
        ) x
        WHERE t.id = x.tag_id
    """)

    # 3. Swap the global-unique name index for a composite unique (name, entity_type).
    op.drop_index('ix_tags_name', table_name='tags')
    op.create_index('ix_tags_name', 'tags', ['name'], unique=False)
    op.create_index('ix_tags_entity_type', 'tags', ['entity_type'], unique=False)
    op.create_unique_constraint('uq_tags_name_entity_type', 'tags', ['name', 'entity_type'])


def downgrade() -> None:
    op.drop_constraint('uq_tags_name_entity_type', 'tags', type_='unique')
    op.drop_index('ix_tags_entity_type', table_name='tags')
    op.drop_index('ix_tags_name', table_name='tags')
    op.create_index('ix_tags_name', 'tags', ['name'], unique=True)
    op.drop_column('tags', 'entity_type')
