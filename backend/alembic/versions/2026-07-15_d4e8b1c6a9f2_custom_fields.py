"""custom fields — definitions table + custom_fields JSON on 4 entities

Admin-defined custom fields for assets, testcases, findings, clients. The
`custom_field_definitions` table holds the schema (admin-managed); each entity
gets a nullable `custom_fields` JSON column holding {field_key: value}. Column
is nullable so the add is safe on populated tables.

Revision ID: d4e8b1c6a9f2
Revises: c7f2a1b9e3d5
"""
from alembic import op
import sqlalchemy as sa

revision = "d4e8b1c6a9f2"
down_revision = "c7f2a1b9e3d5"
branch_labels = None
depends_on = None

_ENTITY_TABLES = ("assets", "testcases", "findings", "clients")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "custom_field_definitions" not in inspector.get_table_names():
        op.create_table(
            "custom_field_definitions",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("entity_type", sa.String(length=20), nullable=False),
            sa.Column("field_key", sa.String(length=64), nullable=False),
            sa.Column("label", sa.String(length=120), nullable=False),
            sa.Column("field_type", sa.String(length=20), nullable=False, server_default="text"),
            sa.Column("options", sa.JSON(), nullable=True),
            sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("help_text", sa.Text(), nullable=True),
            sa.Column("placeholder", sa.String(length=200), nullable=True),
            sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("show_in_list", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("show_in_report", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("created_by", sa.String(), nullable=True),
            sa.Column("updated_by", sa.String(), nullable=True),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("entity_type", "field_key", name="uq_custom_field_entity_key"),
        )
        op.create_index(
            "ix_custom_field_definitions_entity_type",
            "custom_field_definitions", ["entity_type"],
        )

    for table in _ENTITY_TABLES:
        cols = {c["name"] for c in inspector.get_columns(table)}
        if "custom_fields" not in cols:
            op.add_column(table, sa.Column("custom_fields", sa.JSON(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for table in _ENTITY_TABLES:
        cols = {c["name"] for c in inspector.get_columns(table)}
        if "custom_fields" in cols:
            op.drop_column(table, "custom_fields")

    if "custom_field_definitions" in inspector.get_table_names():
        op.drop_index("ix_custom_field_definitions_entity_type", table_name="custom_field_definitions")
        op.drop_table("custom_field_definitions")
