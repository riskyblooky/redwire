"""add SCOPING to engagementstatus enum

The engagement lifecycle has always had 4 phases (SCOPING, PLANNING,
IN_PROGRESS, REPORTING) but the ``EngagementStatus`` enum skipped
SCOPING. The planning-page phase-health logic already assumes SCOPING
sits at index 0 (before PLANNING), which meant every fresh engagement —
defaulting to PLANNING (index 1) — displayed its SCOPING phase as
"completed" the moment it was created. Adding the value here lines the
status ladder up with the phase ladder so PLANNING no longer implicitly
means "past scoping."

Ordinal ``BEFORE PLANNING`` so the enum sort order matches the phase
sort order (matters for anyone who happens to ORDER BY status). Guarded
with IF NOT EXISTS so re-running against a DB that already has the
value is a no-op.

Revision ID: a4c8f5d7e2b9
Revises: f2c1d3e4a5b6
"""
from alembic import op


revision = "a4c8f5d7e2b9"
down_revision = "f2c1d3e4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE engagementstatus ADD VALUE IF NOT EXISTS 'SCOPING' BEFORE 'PLANNING'"
    )


def downgrade() -> None:
    # PostgreSQL doesn't support removing enum values; no-op.
    pass
