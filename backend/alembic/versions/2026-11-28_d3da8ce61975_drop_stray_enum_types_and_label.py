"""drop the enum types no column uses, and findingstatus's FALSE_POSITIVE

753bbc1309ea turned assets.asset_type, cleanup_artifacts.artifact_type,
testcases/testcase_templates.category and vault_items.item_type into strings,
and a2b3c4d5e6f7 did the same for engagements.engagement_type, but neither
dropped the enum types; resourcetype has had no column for as long. Each is
dropped only if no column still uses it.

q8r9s0t1u2v3 added FALSE_POSITIVE to findingstatus, which FindingStatus has
never had: a row holding it can't be loaded. Postgres can't drop an enum
label, so the type is rebuilt without it; any such row becomes CLOSED.

Revision ID: d3da8ce61975
Revises: 4f2d2100ab26
Create Date: 2026-11-28
"""
from alembic import op
import sqlalchemy as sa

revision = "d3da8ce61975"
down_revision = "4f2d2100ab26"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        DO $$
        DECLARE t text;
        BEGIN
            FOREACH t IN ARRAY ARRAY['assettype', 'cleanupartifacttype', 'engagementtype',
                                     'resourcetype', 'testcasecategory', 'vaultitemtype'] LOOP
                IF EXISTS (SELECT 1 FROM pg_type WHERE typname = t AND typnamespace = 'public'::regnamespace)
                   AND NOT EXISTS (
                       SELECT 1 FROM pg_attribute a JOIN pg_type ty ON ty.oid = a.atttypid
                       WHERE ty.typname = t AND a.attnum > 0 AND NOT a.attisdropped) THEN
                    EXECUTE format('DROP TYPE %I', t);
                END IF;
            END LOOP;
        END $$;
    """))

    op.execute(sa.text("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_enum WHERE enumtypid = 'findingstatus'::regtype
                       AND enumlabel = 'FALSE_POSITIVE') THEN
                UPDATE findings SET status = 'CLOSED' WHERE status = 'FALSE_POSITIVE';
                ALTER TYPE findingstatus RENAME TO findingstatus_old;
                CREATE TYPE findingstatus AS ENUM ('OPEN', 'IN_REVIEW', 'VERIFIED', 'CLOSED', 'REMEDIATED');
                ALTER TABLE findings ALTER COLUMN status TYPE findingstatus
                    USING status::text::findingstatus;
                DROP TYPE findingstatus_old;
            END IF;
        END $$;
    """))


def downgrade() -> None:
    # The dropped types come back from the revisions that need them
    # (753bbc1309ea / a2b3c4d5e6f7 create them on their own downgrade).
    op.execute(sa.text("ALTER TYPE findingstatus ADD VALUE IF NOT EXISTS 'FALSE_POSITIVE' AFTER 'CLOSED'"))
