"""Convert resource_type from enum to varchar

Revision ID: fix_resource_type_enum
Revises: add_discussion_tables
Create Date: 2026-01-25 00:38:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'fix_resource_type_enum'
down_revision = 'add_discussion_tables'
branch_labels = None
depends_on = None


def upgrade():
    # Alter threads.resource_type from enum to varchar
    op.execute("ALTER TABLE threads ALTER COLUMN resource_type TYPE VARCHAR(50)")
    
    # Alter activity_logs.resource_type from enum to varchar  
    op.execute("ALTER TABLE activity_logs ALTER COLUMN resource_type TYPE VARCHAR(50)")


def downgrade():
    # Convert back to enum (would need to recreate the enum type)
    pass
