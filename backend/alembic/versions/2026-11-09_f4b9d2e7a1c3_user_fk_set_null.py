"""user FKs: ON DELETE SET NULL so users with history can be deleted

Revision ID: f4b9d2e7a1c3
Revises: e3a8c6d2f1b7
Create Date: 2026-11-09

These foreign keys to users.id had no ON DELETE action, so deleting any
user who had ever logged activity, commented, written a note, etc. failed
with an IntegrityError (500). They now SET NULL — the record (audit row,
note, comment, template) stays and shows its author as deleted — and the
six that were NOT NULL become nullable.

FK names are looked up from the live schema rather than assumed, since
older installs may have been created by create_all rather than alembic.
"""
from alembic import op
import sqlalchemy as sa


revision = "f4b9d2e7a1c3"
down_revision = "e3a8c6d2f1b7"
branch_labels = None
depends_on = None


# (table, column, was NOT NULL)
_COLUMNS = [
    ("activity_logs", "user_id", True),
    ("api_tokens", "created_by", False),
    ("attack_graph_layouts", "pinned_by", True),
    ("comments", "created_by", True),
    ("comments", "resolved_by", False),
    ("dashboard_widgets", "created_by", False),
    ("finding_templates", "published_by", False),
    ("intel_attachments", "created_by", False),
    ("intel_feeds", "created_by", False),
    ("intel_items", "created_by", False),
    ("notes", "created_by", True),
    ("notes", "updated_by", False),
    ("registration_codes", "created_by", True),
    ("runbooks", "published_by", False),
    ("testcase_templates", "published_by", False),
    ("threads", "created_by", True),
]


def _user_fk_names(bind, table, column):
    return [
        fk["name"] for fk in sa.inspect(bind).get_foreign_keys(table)
        if fk["referred_table"] == "users" and fk["constrained_columns"] == [column] and fk["name"]
    ]


def _rebuild(table, column, ondelete):
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(table):
        return
    for name in _user_fk_names(bind, table, column):
        op.drop_constraint(name, table, type_="foreignkey")
    op.create_foreign_key(f"{table}_{column}_fkey", table, "users", [column], ["id"], ondelete=ondelete)


def upgrade():
    for table, column, was_not_null in _COLUMNS:
        if was_not_null and sa.inspect(op.get_bind()).has_table(table):
            op.alter_column(table, column, existing_type=sa.String(), nullable=True)
        _rebuild(table, column, "SET NULL")


def downgrade():
    # Restores the old FK behaviour. NOT NULL is only put back where no row
    # has lost its user since; otherwise the column stays nullable.
    bind = op.get_bind()
    for table, column, was_not_null in _COLUMNS:
        if not sa.inspect(bind).has_table(table):
            continue
        _rebuild(table, column, None)
        if was_not_null:
            nulls = bind.execute(sa.text(f'SELECT count(*) FROM "{table}" WHERE "{column}" IS NULL')).scalar()
            if not nulls:
                op.alter_column(table, column, existing_type=sa.String(), nullable=False)
