"""Initial schema

Revision ID: 001
Revises: 
Create Date: 2026-01-23 23:50:00

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create users table
    op.create_table(
        'users',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('username', sa.String(50), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('hashed_password', sa.String(255), nullable=False),
        sa.Column('full_name', sa.String(255)),
        sa.Column('role', sa.Enum('ADMIN', 'READ_ONLY_ADMIN', 'TEAM_LEAD', 'OPERATOR', 'READ_ONLY', name='userrole'), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('last_login', sa.DateTime()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_users_username', 'users', ['username'], unique=True)
    op.create_index('ix_users_email', 'users', ['email'], unique=True)

    # Create engagements table
    op.create_table(
        'engagements',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('client_name', sa.String(255), nullable=False),
        sa.Column('engagement_type', sa.Enum('EXTERNAL_PENTEST', 'INTERNAL_PENTEST', 'WEB_APPLICATION', 'MOBILE_APPLICATION', 'SOCIAL_ENGINEERING', 'PHYSICAL_SECURITY', 'RED_TEAM', 'PURPLE_TEAM', 'OTHER', name='engagementtype'), nullable=False),
        sa.Column('status', sa.Enum('PLANNING', 'IN_PROGRESS', 'REPORTING', 'COMPLETED', 'ON_HOLD', name='engagementstatus'), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('start_date', sa.DateTime()),
        sa.Column('end_date', sa.DateTime()),
        sa.Column('created_by', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_engagements_name', 'engagements', ['name'])

    # Create findings table
    op.create_table(
        'findings',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('engagement_id', sa.String(), nullable=False),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('severity', sa.Enum('CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO', name='severity'), nullable=False),
        sa.Column('status', sa.Enum('OPEN', 'IN_REVIEW', 'VERIFIED', 'CLOSED', 'FALSE_POSITIVE', name='findingstatus'), nullable=False),
        sa.Column('affected_asset', sa.String(255)),
        sa.Column('steps_to_reproduce', sa.Text()),
        sa.Column('impact', sa.Text()),
        sa.Column('remediation', sa.Text()),
        sa.Column('references', sa.Text()),
        sa.Column('cvss_score', sa.Float()),
        sa.Column('cvss_vector', sa.String(100)),
        sa.Column('created_by', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.ForeignKeyConstraint(['engagement_id'], ['engagements.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_findings_title', 'findings', ['title'])
    op.create_index('ix_findings_severity', 'findings', ['severity'])

    # Create assets table
    op.create_table(
        'assets',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('engagement_id', sa.String(), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('asset_type', sa.Enum('IP_ADDRESS', 'DOMAIN', 'URL', 'APPLICATION', 'SERVER', 'NETWORK', 'OTHER', name='assettype'), nullable=False),
        sa.Column('identifier', sa.String(500), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('notes', sa.Text( )),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['engagement_id'], ['engagements.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_assets_name', 'assets', ['name'])

    # Create evidence table
    op.create_table(
        'evidence',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('finding_id', sa.String(), nullable=False),
        sa.Column('filename', sa.String(255), nullable=False),
        sa.Column('original_filename', sa.String(255), nullable=False),
        sa.Column('file_path', sa.String(500), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=False),
        sa.Column('mime_type', sa.String(100)),
        sa.Column('description', sa.String(500)),
        sa.Column('uploaded_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['finding_id'], ['findings.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create testcases table
    op.create_table(
        'testcases',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('engagement_id', sa.String()),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('category', sa.Enum('RECONNAISSANCE', 'SCANNING', 'EXPLOITATION', 'POST_EXPLOITATION', 'PRIVILEGE_ESCALATION', 'PERSISTENCE', 'LATERAL_MOVEMENT', 'WEB_APPLICATION', 'SOCIAL_ENGINEERING', 'PHYSICAL', 'OTHER', name='testcasecategory'), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('steps', sa.Text()),
        sa.Column('expected_result', sa.Text()),
        sa.Column('actual_result', sa.Text()),
        sa.Column('is_executed', sa.Boolean(), server_default='false'),
        sa.Column('is_successful', sa.Boolean()),
        sa.Column('notes', sa.Text()),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['engagement_id'], ['engagements.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_testcases_title', 'testcases', ['title'])

    # Create calendar_events table
    op.create_table(
        'calendar_events',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('start_time', sa.DateTime(), nullable=False),
        sa.Column('end_time', sa.DateTime(), nullable=False),
        sa.Column('location', sa.String(255)),
        sa.Column('is_all_day', sa.Boolean(), server_default='false'),
        sa.Column('created_by', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_calendar_events_start_time', 'calendar_events', ['start_time'])

    # Admin user is now seeded at application startup via env vars
    # (ADMIN_EMAIL, ADMIN_PASSWORD, ADMIN_USERNAME) — see main.py lifespan


def downgrade() -> None:
    op.drop_table('calendar_events')
    op.drop_table('testcases')
    op.drop_table('evidence')
    op.drop_table('assets')
    op.drop_table('findings')
    op.drop_table('engagements')
    op.drop_table('users')
    
    op.execute("DROP TYPE IF EXISTS testcasecategory;")
    op.execute("DROP TYPE IF EXISTS assettype;")
    op.execute("DROP TYPE IF EXISTS findingstatus;")
    op.execute("DROP TYPE IF EXISTS severity;")
    op.execute("DROP TYPE IF EXISTS engagementtype;")
    op.execute("DROP TYPE IF EXISTS engagementstatus;")
    op.execute("DROP TYPE IF EXISTS userrole;")
