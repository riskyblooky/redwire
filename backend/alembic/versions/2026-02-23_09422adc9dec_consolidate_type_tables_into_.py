"""consolidate type tables into configurable_types

Revision ID: 09422adc9dec
Revises: 753bbc1309ea
Create Date: 2026-02-23 07:04:22.309184+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '09422adc9dec'
down_revision: Union[str, None] = '753bbc1309ea'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Drop the old FK first so we can freely remap client_type_id values
    op.drop_constraint('clients_client_type_id_fkey', 'clients', type_='foreignkey')

    # 2. Copy client_types into configurable_types (skip if name already exists)
    conn.execute(sa.text("""
        INSERT INTO configurable_types (id, category, name, description, color, is_system, sort_order)
        SELECT id, 'client', name, description, color, is_system, sort_order
        FROM client_types
        ON CONFLICT (category, name) DO NOTHING
    """))

    # 3. Remap clients.client_type_id for rows where the old ID wasn't inserted
    #    (because a matching name already existed in configurable_types with a different ID)
    conn.execute(sa.text("""
        UPDATE clients
        SET client_type_id = ct.id
        FROM client_types AS old_ct
        JOIN configurable_types AS ct ON ct.category = 'client' AND ct.name = old_ct.name
        WHERE clients.client_type_id = old_ct.id
          AND clients.client_type_id != ct.id
    """))

    # 4. Copy engagement_types into configurable_types
    conn.execute(sa.text("""
        INSERT INTO configurable_types (id, category, name, description, color, is_system, sort_order)
        SELECT id, 'engagement', name, description, color, is_system, sort_order
        FROM engagement_types
        ON CONFLICT (category, name) DO NOTHING
    """))

    # 5. Add new FK pointing to configurable_types
    op.create_foreign_key(None, 'clients', 'configurable_types', ['client_type_id'], ['id'], ondelete='SET NULL')

    # 6. Drop old tables
    op.drop_table('client_types')
    op.drop_table('engagement_types')


def downgrade() -> None:
    op.drop_constraint(None, 'clients', type_='foreignkey')
    op.create_foreign_key('clients_client_type_id_fkey', 'clients', 'client_types', ['client_type_id'], ['id'], ondelete='SET NULL')
    op.create_table('engagement_types',
    sa.Column('id', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('name', sa.VARCHAR(length=100), autoincrement=False, nullable=False),
    sa.Column('description', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('color', sa.VARCHAR(length=7), server_default=sa.text("'#6366f1'::character varying"), autoincrement=False, nullable=True),
    sa.Column('is_system', sa.BOOLEAN(), server_default=sa.text('false'), autoincrement=False, nullable=False),
    sa.Column('sort_order', sa.INTEGER(), server_default=sa.text('0'), autoincrement=False, nullable=False),
    sa.PrimaryKeyConstraint('id', name='engagement_types_pkey'),
    sa.UniqueConstraint('name', name='engagement_types_name_key')
    )
    op.create_table('client_types',
    sa.Column('id', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('name', sa.VARCHAR(length=100), autoincrement=False, nullable=False),
    sa.Column('description', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('color', sa.VARCHAR(length=7), server_default=sa.text("'#6366f1'::character varying"), autoincrement=False, nullable=True),
    sa.Column('is_system', sa.BOOLEAN(), server_default=sa.text('false'), autoincrement=False, nullable=False),
    sa.Column('sort_order', sa.INTEGER(), server_default=sa.text('0'), autoincrement=False, nullable=False),
    sa.PrimaryKeyConstraint('id', name='client_types_pkey'),
    sa.UniqueConstraint('name', name='client_types_name_key')
    )
