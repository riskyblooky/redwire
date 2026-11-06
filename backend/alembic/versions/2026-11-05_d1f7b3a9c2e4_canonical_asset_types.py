"""assets.asset_type — rewrite legacy spellings to configured type names

Older clients, imports and the MCP server stored values like IP_ADDRESS,
host or web_application, which the asset edit form's Type dropdown can't
display. Map every value onto a configured asset type (case/separator-
insensitive match, then the legacy alias table in utils/asset_types.py);
values that match nothing become "Other". Writes are canonicalized from now
on, so this only has to run once. Data-only; downgrade is a no-op.

Revision ID: d1f7b3a9c2e4
Revises: c9e5a1f3b4d6
Create Date: 2026-11-05
"""
from alembic import op
import sqlalchemy as sa

revision = "d1f7b3a9c2e4"
down_revision = "c9e5a1f3b4d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from utils.asset_types import canonical_name

    bind = op.get_bind()
    names = [r[0] for r in bind.execute(sa.text(
        "SELECT name FROM configurable_types WHERE category = 'asset' ORDER BY sort_order"
    ))]
    if not names:
        return
    other = canonical_name("Other", names)
    for (value,) in bind.execute(sa.text("SELECT DISTINCT asset_type FROM assets")).all():
        target = canonical_name(value, names) or other
        if target and target != value:
            bind.execute(
                sa.text("UPDATE assets SET asset_type = :t WHERE asset_type IS NOT DISTINCT FROM :v"),
                {"t": target, "v": value},
            )


def downgrade() -> None:
    # The original spellings aren't recoverable and nothing depends on them.
    pass
