"""add intelligence tables

Revision ID: k1l2m3n4o5p6
Revises: j0k1l2m3n4o5
Create Date: 2026-03-13 22:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'k1l2m3n4o5p6'
down_revision: Union[str, None] = 'j0k1l2m3n4o5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Intel feeds table
    op.create_table('intel_feeds',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('url', sa.String(length=1000), nullable=False),
        sa.Column('feed_type', sa.String(length=20), server_default='RSS', nullable=True),
        sa.Column('enabled', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('last_fetched_at', sa.DateTime(), nullable=True),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    # Intel items table
    op.create_table('intel_items',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('title', sa.String(length=500), nullable=False),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('source', sa.String(length=255), nullable=True),
        sa.Column('source_url', sa.Text(), nullable=True),
        sa.Column('item_type', sa.String(length=20), server_default='OTHER', nullable=False),
        sa.Column('severity', sa.String(length=20), nullable=True),
        sa.Column('cve_id', sa.String(length=50), nullable=True),
        sa.Column('published_at', sa.DateTime(), nullable=True),
        sa.Column('feed_id', sa.String(), nullable=True),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['feed_id'], ['intel_feeds.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_intel_items_title', 'intel_items', ['title'])
    op.create_index('ix_intel_items_cve_id', 'intel_items', ['cve_id'])

    # Association tables
    op.create_table('intel_item_findings',
        sa.Column('intel_item_id', sa.String(), nullable=False),
        sa.Column('finding_id', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['intel_item_id'], ['intel_items.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['finding_id'], ['findings.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('intel_item_id', 'finding_id'),
    )

    op.create_table('intel_item_testcases',
        sa.Column('intel_item_id', sa.String(), nullable=False),
        sa.Column('testcase_id', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['intel_item_id'], ['intel_items.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['testcase_id'], ['testcases.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('intel_item_id', 'testcase_id'),
    )

    op.create_table('intel_item_notes',
        sa.Column('intel_item_id', sa.String(), nullable=False),
        sa.Column('note_id', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['intel_item_id'], ['intel_items.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['note_id'], ['notes.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('intel_item_id', 'note_id'),
    )

    # Seed default feeds
    op.execute("""
        INSERT INTO intel_feeds (id, name, url, feed_type, enabled, created_at)
        VALUES
            ('feed-cisa-kev', 'CISA Known Exploited Vulnerabilities', 'https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json', 'JSON', true, NOW()),
            ('feed-exploit-db', 'Exploit-DB', 'https://www.exploit-db.com/rss.xml', 'RSS', true, NOW()),
            ('feed-hacker-news', 'The Hacker News', 'https://feeds.feedburner.com/TheHackersNews', 'RSS', true, NOW()),
            ('feed-nvd-cve', 'NVD CVE Feed', 'https://nvd.nist.gov/feeds/xml/cve/misc/nvd-rss.xml', 'RSS', true, NOW()),
            ('feed-krebs', 'Krebs on Security', 'https://krebsonsecurity.com/feed/', 'RSS', true, NOW()),
            ('feed-bleeping', 'BleepingComputer', 'https://www.bleepingcomputer.com/feed/', 'RSS', true, NOW()),
            ('feed-packet-storm', 'Packet Storm Security', 'https://packetstormsecurity.com/feeds/', 'RSS', true, NOW()),
            ('feed-nist-alerts', 'US-CERT Alerts', 'https://www.cisa.gov/uscert/ncas/alerts.xml', 'RSS', true, NOW())
        ON CONFLICT (id) DO NOTHING
    """)


def downgrade() -> None:
    op.drop_table('intel_item_notes')
    op.drop_table('intel_item_testcases')
    op.drop_table('intel_item_findings')
    op.drop_index('ix_intel_items_cve_id', table_name='intel_items')
    op.drop_index('ix_intel_items_title', table_name='intel_items')
    op.drop_table('intel_items')
    op.drop_table('intel_feeds')
