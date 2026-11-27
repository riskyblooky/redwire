"""drop plugin enrichment rows whose asset is gone

shodan_enricher ("enrich:<asset id>") and servicenow_cmdb ("cmdb:<asset id>")
store per-asset results in plugin_settings, and nothing deleted them with
the asset. New deletes clean up in the same flush (models/plugin.py); this
removes the ones already left behind. Not reversible — the rows describe
assets that no longer exist.

Revision ID: 4f2d2100ab26
Revises: 0e61da43042f
Create Date: 2026-11-26
"""
from alembic import op
import sqlalchemy as sa

revision = "4f2d2100ab26"
down_revision = "0e61da43042f"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(sa.text("""
        DELETE FROM plugin_settings ps
        WHERE ((ps.plugin_id = 'shodan_enricher' AND ps.key LIKE 'enrich:%')
            OR (ps.plugin_id = 'servicenow_cmdb' AND ps.key LIKE 'cmdb:%'))
          AND NOT EXISTS (SELECT 1 FROM assets a WHERE a.id = right(ps.key, 36))
    """))


def downgrade():
    pass
