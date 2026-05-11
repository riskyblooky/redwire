"""add_groups_and_rbac

Revision ID: b6d8490e6d62
Revises: 001
Create Date: 2026-01-25 02:08:39.038250+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b6d8490e6d62'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = inspector.get_table_names()

    # ── Create tables that were previously created by SQLAlchemy create_all ──
    if 'engagement_roles' not in existing:
        op.create_table('engagement_roles',
            sa.Column('id', sa.String(), nullable=False),
            sa.Column('name', sa.String(length=100), nullable=False),
            sa.Column('description', sa.String(length=500), nullable=True),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_engagement_roles_name'), 'engagement_roles', ['name'], unique=True)

    if 'groups' not in existing:
        op.create_table('groups',
            sa.Column('id', sa.String(), nullable=False),
            sa.Column('name', sa.String(length=100), nullable=False),
            sa.Column('description', sa.String(length=500), nullable=True),
            sa.Column('is_system', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('is_default', sa.Boolean(), nullable=False, server_default='false'),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_groups_name'), 'groups', ['name'], unique=True)

    if 'user_groups' not in existing:
        op.create_table('user_groups',
            sa.Column('user_id', sa.String(), nullable=False),
            sa.Column('group_id', sa.String(), nullable=False),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['group_id'], ['groups.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('user_id', 'group_id'),
        )

    if 'engagement_assignments' not in existing:
        op.create_table('engagement_assignments',
            sa.Column('user_id', sa.String(), nullable=False),
            sa.Column('engagement_id', sa.String(), nullable=False),
            sa.Column('role_id', sa.String(), nullable=True),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['engagement_id'], ['engagements.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['role_id'], ['engagement_roles.id'], ondelete='SET NULL'),
            sa.PrimaryKeyConstraint('user_id', 'engagement_id'),
        )
    else:
        # Table already existed (dev DB) — just add the role_id column
        op.add_column('engagement_assignments', sa.Column('role_id', sa.String(), nullable=True))
        op.create_foreign_key(None, 'engagement_assignments', 'engagement_roles', ['role_id'], ['id'], ondelete='SET NULL')

    # ── FK and index adjustments (inspector-based for PostgreSQL safety) ──
    # PostgreSQL aborts the whole transaction on any DDL error, so we must
    # check existence before dropping instead of using try/except.

    def _fk_names(table):
        return {fk['name'] for fk in inspector.get_foreign_keys(table)}

    def _index_names(table):
        return {idx['name'] for idx in inspector.get_indexes(table)}

    def _unique_constraint_names(table):
        return {uc['name'] for uc in inspector.get_unique_constraints(table)}

    # Drop CASCADE FKs and recreate without CASCADE (only on dev DBs that have them)
    for table, fk_name, ref_table, local_cols, remote_cols in [
        ('assets', 'assets_engagement_id_fkey', 'engagements', ['engagement_id'], ['id']),
        ('evidence', 'evidence_finding_id_fkey', 'findings', ['finding_id'], ['id']),
        ('findings', 'findings_engagement_id_fkey', 'engagements', ['engagement_id'], ['id']),
        ('testcases', 'testcases_engagement_id_fkey', 'engagements', ['engagement_id'], ['id']),
    ]:
        if fk_name in _fk_names(table):
            op.drop_constraint(fk_name, table, type_='foreignkey')
            op.create_foreign_key(None, table, ref_table, local_cols, remote_cols)

    # Drop legacy unique constraints if they exist (dev DBs may have both constraint + index)
    for table, uc_name in [('users', 'users_email_key'), ('users', 'users_username_key')]:
        if uc_name in _unique_constraint_names(table):
            op.drop_constraint(uc_name, table, type_='unique')

    # Recreate indexes (drop first only if they exist)
    for idx_name, table, cols in [
        ('ix_users_email', 'users', ['email']),
        ('ix_users_username', 'users', ['username']),
    ]:
        if idx_name in _index_names(table):
            op.drop_index(idx_name, table_name=table)
        op.create_index(op.f(idx_name), table, cols, unique=True)
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.create_index('ix_users_username', 'users', ['username'], unique=False)
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.create_index('ix_users_email', 'users', ['email'], unique=False)
    op.create_unique_constraint('users_username_key', 'users', ['username'])
    op.create_unique_constraint('users_email_key', 'users', ['email'])
    op.drop_constraint(None, 'testcases', type_='foreignkey')
    op.create_foreign_key('testcases_engagement_id_fkey', 'testcases', 'engagements', ['engagement_id'], ['id'], ondelete='CASCADE')
    op.drop_constraint(None, 'findings', type_='foreignkey')
    op.create_foreign_key('findings_engagement_id_fkey', 'findings', 'engagements', ['engagement_id'], ['id'], ondelete='CASCADE')
    op.drop_constraint(None, 'evidence', type_='foreignkey')
    op.create_foreign_key('evidence_finding_id_fkey', 'evidence', 'findings', ['finding_id'], ['id'], ondelete='CASCADE')
    op.drop_constraint(None, 'engagement_assignments', type_='foreignkey')
    op.drop_column('engagement_assignments', 'role_id')
    op.drop_constraint(None, 'assets', type_='foreignkey')
    op.create_foreign_key('assets_engagement_id_fkey', 'assets', 'engagements', ['engagement_id'], ['id'], ondelete='CASCADE')
    # ### end Alembic commands ###
