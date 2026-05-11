"""add_clients_and_client_types

Revision ID: b3c4d5e6f7g8
Revises: a1b2c3d4f7g8
Create Date: 2026-02-08
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = 'b3c4d5e6f7g8'
down_revision = 'a1b2c3d4f7g8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create client_types table
    op.create_table(
        'client_types',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('color', sa.String(7), nullable=True, server_default='#6366f1'),
        sa.Column('is_system', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )

    # Create clients table
    op.create_table(
        'clients',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('client_type_id', sa.String(), sa.ForeignKey('client_types.id', ondelete='SET NULL'), nullable=True),
        sa.Column('parent_id', sa.String(), sa.ForeignKey('clients.id', ondelete='SET NULL'), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('contact_name', sa.String(255), nullable=True),
        sa.Column('contact_email', sa.String(255), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('created_by', sa.String(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('updated_by', sa.String(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_clients_name', 'clients', ['name'])

    # Add client_id to engagements table
    op.add_column('engagements', sa.Column('client_id', sa.String(), nullable=True))
    op.create_foreign_key(
        'fk_engagements_client_id',
        'engagements', 'clients',
        ['client_id'], ['id'],
        ondelete='SET NULL'
    )
    op.create_index('ix_engagements_client_id', 'engagements', ['client_id'])

    # Data migration: create client records from existing unique client_name values
    # 1. Seed the default "Organization" client type if not present
    op.execute("""
        INSERT INTO client_types (id, name, description, color, is_system, sort_order)
        SELECT gen_random_uuid()::text, 'Organization', 'Top-level organization or company', '#6366f1', true, 0
        WHERE NOT EXISTS (SELECT 1 FROM client_types WHERE name = 'Organization')
    """)

    # 2. Create client records from unique client_name values
    op.execute("""
        INSERT INTO clients (id, name, client_type_id, sort_order, created_at, updated_at)
        SELECT
            gen_random_uuid()::text,
            e.client_name,
            (SELECT id FROM client_types WHERE name = 'Organization' LIMIT 1),
            ROW_NUMBER() OVER (ORDER BY e.client_name),
            NOW(),
            NOW()
        FROM (SELECT DISTINCT client_name FROM engagements WHERE client_name IS NOT NULL AND client_name != '') e
    """)

    # 3. Link engagements to newly created client records
    op.execute("""
        UPDATE engagements
        SET client_id = c.id
        FROM clients c
        WHERE engagements.client_name = c.name
    """)


def downgrade() -> None:
    op.drop_index('ix_engagements_client_id', table_name='engagements')
    op.drop_constraint('fk_engagements_client_id', 'engagements', type_='foreignkey')
    op.drop_column('engagements', 'client_id')
    op.drop_index('ix_clients_name', table_name='clients')
    op.drop_table('clients')
    op.drop_table('client_types')
