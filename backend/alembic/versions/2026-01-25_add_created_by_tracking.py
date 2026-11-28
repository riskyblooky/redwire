"""Add created_by to assets and testcases

Revision ID: add_created_by_tracking
Revises: fix_resource_type_enum
Create Date: 2026-01-25 11:15:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

# revision identifiers, used by Alembic.
revision = 'add_created_by_tracking'
down_revision = 'aa206dcd2453'
branch_labels = None
depends_on = None

def upgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    
    # Check and add for assets
    if 'created_by' not in [c['name'] for c in inspector.get_columns('assets')]:
        op.add_column('assets', sa.Column('created_by', sa.String(), nullable=True))
        
        # Set default user - get first user
        op.execute("UPDATE assets SET created_by = (SELECT id FROM users LIMIT 1) WHERE created_by IS NULL")
        
        # Now make it non-nullable if we have a user
        op.alter_column('assets', 'created_by', nullable=False)

    # Check and add for testcases
    if 'created_by' not in [c['name'] for c in inspector.get_columns('testcases')]:
        op.add_column('testcases', sa.Column('created_by', sa.String(), nullable=True))
        
        # Set default user
        op.execute("UPDATE testcases SET created_by = (SELECT id FROM users LIMIT 1) WHERE created_by IS NULL")
        
        # Now make it non-nullable
        op.alter_column('testcases', 'created_by', nullable=False)


def downgrade():
    op.drop_column('testcases', 'created_by')
    op.drop_column('assets', 'created_by')
