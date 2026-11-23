"""user delete keeps org automation rules and finding reviews

Deleting a user cascaded to every org automation rule they had written
(``automation_rules.created_by``) and every review they had left
(``finding_reviews.reviewer_id``). Both become ON DELETE SET NULL, like the
other author references; personal rules (``owner_user_id``) still go with
their owner.

Revision ID: a3e7c1d9f4b2
Revises: d7b2e5f8a3c9
Create Date: 2026-11-23
"""
from alembic import op

revision = "a3e7c1d9f4b2"
down_revision = "d7b2e5f8a3c9"
branch_labels = None
depends_on = None

_FKS = [
    ("automation_rules", "created_by", "automation_rules_created_by_fkey"),
    ("finding_reviews", "reviewer_id", "finding_reviews_reviewer_id_fkey"),
]
# Rows orphaned since the upgrade can't satisfy NOT NULL again; downgrade
# drops them (what the old CASCADE would have done).
_ORPHANS = {
    "automation_rules": "DELETE FROM automation_rules WHERE created_by IS NULL",
    "finding_reviews": "DELETE FROM finding_reviews WHERE reviewer_id IS NULL",
}


def upgrade():
    for table, col, name in _FKS:
        op.alter_column(table, col, nullable=True)
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(name, table, "users", [col], ["id"], ondelete="SET NULL")


def downgrade():
    for table, col, name in _FKS:
        op.execute(_ORPHANS[table])
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(name, table, "users", [col], ["id"], ondelete="CASCADE")
        op.alter_column(table, col, nullable=False)
