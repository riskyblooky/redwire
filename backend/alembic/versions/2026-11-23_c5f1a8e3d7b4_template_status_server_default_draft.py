"""template status server default matches the ORM: DRAFT

finding_templates, testcase_templates and runbooks had
server_default 'PUBLISHED' (from the migration that published existing rows
when the review workflow arrived) while the ORM defaults new rows to DRAFT.
A row inserted outside the ORM skipped review. Existing rows are unchanged.

Revision ID: c5f1a8e3d7b4
Revises: b8d4f2a6c1e9
Create Date: 2026-11-23
"""
from alembic import op
import sqlalchemy as sa

revision = "c5f1a8e3d7b4"
down_revision = "b8d4f2a6c1e9"
branch_labels = None
depends_on = None

_TABLES = ("finding_templates", "testcase_templates", "runbooks")


def upgrade():
    for t in _TABLES:
        op.alter_column(t, "status", server_default=sa.text("'DRAFT'::templatestatus"))


def downgrade():
    for t in _TABLES:
        op.alter_column(t, "status", server_default=sa.text("'PUBLISHED'::templatestatus"))
