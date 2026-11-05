"""runbook_items frozen template content — snapshot at approve time

Revision ID: b8d4f0e2a3c5
Revises: a7c3e9d1f2b4
Create Date: 2026-11-04
"""
from alembic import op
import sqlalchemy as sa

revision = "b8d4f0e2a3c5"
down_revision = "a7c3e9d1f2b4"
branch_labels = None
depends_on = None

_COLS = [
    ("frozen_title", sa.String(500)),
    ("frozen_category", sa.String(100)),
    ("frozen_description", sa.Text()),
    ("frozen_steps", sa.Text()),
    ("frozen_expected_result", sa.Text()),
    ("frozen_at", sa.DateTime()),
]


def upgrade() -> None:
    for name, type_ in _COLS:
        op.add_column("runbook_items", sa.Column(name, type_, nullable=True))
    # Freeze already-published runbooks at their templates' current content,
    # for items whose template is itself PUBLISHED (the approve-time gate).
    # Anything else stays unfrozen and keeps hitting the apply-time gate.
    op.execute(
        """
        UPDATE runbook_items ri SET
            frozen_title = t.title,
            frozen_category = t.category,
            frozen_description = t.description,
            frozen_steps = t.steps,
            frozen_expected_result = t.expected_result,
            frozen_at = now() AT TIME ZONE 'utc'
        FROM runbooks r, testcase_templates t
        WHERE ri.runbook_id = r.id AND ri.template_id = t.id
          AND r.status = 'PUBLISHED' AND t.status = 'PUBLISHED'
        """
    )


def downgrade() -> None:
    for name, _ in reversed(_COLS):
        op.drop_column("runbook_items", name)
