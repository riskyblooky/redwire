"""Add engagement_types table

Revision ID: a2b3c4d5e6f7
Revises: 20260209030100
Create Date: 2026-02-09

"""
from alembic import op
import sqlalchemy as sa
import uuid


# revision identifiers, used by Alembic.
revision = 'a2b3c4d5e6f7'
down_revision = '20260209030100'
branch_labels = None
depends_on = None


# Default engagement types that match the old enum values
DEFAULT_TYPES = [
    {"name": "External Pentest", "description": "External Penetration Test", "color": "#ef4444", "is_system": True, "sort_order": 0},
    {"name": "Internal Pentest", "description": "Internal Penetration Test", "color": "#f97316", "is_system": True, "sort_order": 1},
    {"name": "Web Application", "description": "Web Application Assessment", "color": "#eab308", "is_system": True, "sort_order": 2},
    {"name": "Mobile Application", "description": "Mobile Application Assessment", "color": "#22c55e", "is_system": True, "sort_order": 3},
    {"name": "Social Engineering", "description": "Social Engineering", "color": "#14b8a6", "is_system": True, "sort_order": 4},
    {"name": "Physical Security", "description": "Physical Security Assessment", "color": "#3b82f6", "is_system": True, "sort_order": 5},
    {"name": "Red Team", "description": "Red Team Exercise", "color": "#dc2626", "is_system": True, "sort_order": 6},
    {"name": "Purple Team", "description": "Purple Team Exercise", "color": "#7c3aed", "is_system": True, "sort_order": 7},
    {"name": "Other", "description": "Other", "color": "#64748b", "is_system": False, "sort_order": 8},
]


def upgrade() -> None:
    # Create engagement_types table
    op.create_table(
        'engagement_types',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False, unique=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('color', sa.String(7), nullable=True, server_default='#6366f1'),
        sa.Column('is_system', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
    )

    # Seed default types
    engagement_types_table = sa.table(
        'engagement_types',
        sa.column('id', sa.String),
        sa.column('name', sa.String),
        sa.column('description', sa.Text),
        sa.column('color', sa.String),
        sa.column('is_system', sa.Boolean),
        sa.column('sort_order', sa.Integer),
    )

    for t in DEFAULT_TYPES:
        op.execute(
            engagement_types_table.insert().values(
                id=str(uuid.uuid4()),
                **t
            )
        )

    # Change engagement_type column from enum to varchar
    # SQLite doesn't have ALTER COLUMN, so we need to handle this carefully
    # For PostgreSQL/MySQL, we'd use alter_column. For SQLite, the column is already
    # stored as text since SQLAlchemy SQLite enums are stored as strings.
    # We'll use batch mode which works for SQLite:
    with op.batch_alter_table('engagements') as batch_op:
        batch_op.alter_column(
            'engagement_type',
            type_=sa.String(100),
            existing_type=sa.Enum(
                'EXTERNAL_PENTEST', 'INTERNAL_PENTEST', 'WEB_APPLICATION',
                'MOBILE_APPLICATION', 'SOCIAL_ENGINEERING', 'PHYSICAL_SECURITY',
                'RED_TEAM', 'PURPLE_TEAM', 'OTHER',
                name='engagementtype'
            ),
            existing_nullable=False
        )


def downgrade() -> None:
    with op.batch_alter_table('engagements') as batch_op:
        batch_op.alter_column(
            'engagement_type',
            type_=sa.Enum(
                'EXTERNAL_PENTEST', 'INTERNAL_PENTEST', 'WEB_APPLICATION',
                'MOBILE_APPLICATION', 'SOCIAL_ENGINEERING', 'PHYSICAL_SECURITY',
                'RED_TEAM', 'PURPLE_TEAM', 'OTHER',
                name='engagementtype'
            ),
            existing_type=sa.String(100),
            existing_nullable=False
        )
    op.drop_table('engagement_types')
