"""system delta widget: relative "prior 7 days" instead of frozen dates

sys-findings-week-delta compared the last 7 days with a custom range whose
dates were computed when the backend module loaded and then seeded into
the row, so it compared against a fixed week from the first boot. Switch
its second query to the new relative "prior_7d" range — only if it still
holds the custom range the seeder wrote.

Revision ID: c4f1a7e3b8d2
Revises: b2e7c4a9d1f6
Create Date: 2026-11-21
"""
import json

import sqlalchemy as sa
from alembic import op

revision = "c4f1a7e3b8d2"
down_revision = "b2e7c4a9d1f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    row = bind.execute(sa.text(
        "SELECT config FROM dashboard_widgets WHERE id = 'sys-findings-week-delta'"
    )).first()
    if row is None or row[0] is None:
        return
    config = row[0] if isinstance(row[0], dict) else json.loads(row[0])
    queries = config.get("queries") or []
    if len(queries) < 2 or queries[1].get("date_range") != "custom":
        return
    q = dict(queries[1])
    q.pop("date_start", None)
    q.pop("date_end", None)
    q["date_range"] = "prior_7d"
    config["queries"] = [queries[0], q, *queries[2:]]
    bind.execute(sa.text(
        "UPDATE dashboard_widgets SET config = CAST(:c AS json) WHERE id = 'sys-findings-week-delta'"
    ), {"c": json.dumps(config)})


def downgrade() -> None:
    pass
