"""align foreign-key ON DELETE rules with the ORM cascades

The ORM deleted an engagement's assets, evidence, findings, test cases,
threads and vault items, a finding's evidence, a thread's comments and an
intel feed's items, but their foreign keys were NO ACTION (SET NULL for
intel items), so the database refused — or, for intel items, contradicted —
the same delete done outside the ORM. A test case's evidence is unlinked by
the ORM; its key now says SET NULL too. The ORM cascades stay, so per-row
hooks (stored-object cleanup) still run; the database rule is the backstop.

Revision ID: 0e61da43042f
Revises: d9e2b7c4a1f6
Create Date: 2026-11-26
"""
from alembic import op
import sqlalchemy as sa

revision = "0e61da43042f"
down_revision = "d9e2b7c4a1f6"
branch_labels = None
depends_on = None

# (table, column, referred table, new rule, old rule)
_FKS = [
    ("assets", "engagement_id", "engagements", "CASCADE", None),
    ("evidence", "engagement_id", "engagements", "CASCADE", None),
    ("evidence", "finding_id", "findings", "CASCADE", None),
    ("evidence", "testcase_id", "testcases", "SET NULL", None),
    ("findings", "engagement_id", "engagements", "CASCADE", None),
    ("testcases", "engagement_id", "engagements", "CASCADE", None),
    ("threads", "engagement_id", "engagements", "CASCADE", None),
    ("vault_items", "engagement_id", "engagements", "CASCADE", None),
    ("comments", "thread_id", "threads", "CASCADE", None),
    ("intel_items", "feed_id", "intel_feeds", "CASCADE", "SET NULL"),
]


def _set_rule(table, column, referred, rule):
    # Look the constraint up instead of assuming its name: installs created
    # at different times carry different auto-generated names.
    insp = sa.inspect(op.get_bind())
    names = [fk["name"] for fk in insp.get_foreign_keys(table)
             if fk["constrained_columns"] == [column] and fk["referred_table"] == referred]
    for name in names:
        op.drop_constraint(name, table, type_="foreignkey")
    op.create_foreign_key(f"{table}_{column}_fkey", table, referred, [column], ["id"], ondelete=rule)


def upgrade():
    for table, column, referred, new, _old in _FKS:
        _set_rule(table, column, referred, new)


def downgrade():
    for table, column, referred, _new, old in _FKS:
        _set_rule(table, column, referred, old)
