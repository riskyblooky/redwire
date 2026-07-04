"""add report_themes.is_system + pin existing default as system

Revision ID: d347b4e5f6a1
Revises: c1a3f7b8e2d4
Create Date: 2026-07-04 12:00:00.000000+00:00

GHSA-3m9c-7f84-9cm2 follow-up. That advisory gated the ``is_default``
flag to admins so a takeover attack was impossible; this migration adds
a second guard so an admin who intentionally or accidentally deletes
the last is_default row doesn't break report generation for every
subsequent engagement.

Adds ``is_system`` (Boolean, NOT NULL, default false) to the
report_themes table. The seeded default theme (via
seed_defaults.seed_default_report_theme) is pinned as is_system=True
under a deterministic id — the delete endpoint refuses to delete it
and the report generator falls back to it as an ultimate fallback
after the user-marked default lookup.

Migration behavior:
  1. Add the column with server_default=false so existing rows get
     False and the DDL succeeds even on populated tables.
  2. If there's already a row with the deterministic system id (fresh
     install right after this migration ran alongside seed), set
     is_system=True on it — otherwise seed_default_report_theme
     creates it on the next boot.
  3. If there's no such row but there IS an is_default=True row, DO
     NOT re-pin it as system — the operator may have customized it.
     seed_default_report_theme will drop the fresh system row alongside.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d347b4e5f6a1"
down_revision: Union[str, None] = "c1a3f7b8e2d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SYSTEM_ID = "00000000-0000-0000-0000-00000000d347"


def upgrade() -> None:
    op.add_column(
        "report_themes",
        sa.Column(
            "is_system",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    # If the deterministic system row happens to exist already (someone
    # ran the newer seed against the pre-column schema in a dev branch,
    # etc.), pin the marker. Otherwise the seeder will drop the row on
    # the next boot.
    op.execute(f"""
        UPDATE report_themes
        SET is_system = TRUE
        WHERE id = '{SYSTEM_ID}';
    """)


def downgrade() -> None:
    op.drop_column("report_themes", "is_system")
