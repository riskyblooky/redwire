"""add skills tables

Revision ID: p5q6r7s8t9u0
Revises: n4o5p6q7r8s9
Create Date: 2026-03-14 21:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'p5q6r7s8t9u0'
down_revision: Union[str, None] = 'n4o5p6q7r8s9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'skill_categories',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('color', sa.String(length=7), nullable=True, server_default='#6366f1'),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )

    op.create_table(
        'skills',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('category_id', sa.String(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.ForeignKeyConstraint(['category_id'], ['skill_categories.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('category_id', 'name', name='uq_skill_category_name'),
    )
    op.create_index('ix_skills_category_id', 'skills', ['category_id'])

    op.create_table(
        'user_skills',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('skill_id', sa.String(), nullable=False),
        sa.Column('level', sa.Integer(), nullable=False, server_default='0'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['skill_id'], ['skills.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'skill_id', name='uq_user_skill'),
    )
    op.create_index('ix_user_skills_user_id', 'user_skills', ['user_id'])
    op.create_index('ix_user_skills_skill_id', 'user_skills', ['skill_id'])

    op.create_table(
        'engagement_skills',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('engagement_id', sa.String(), nullable=False),
        sa.Column('skill_id', sa.String(), nullable=False),
        sa.Column('min_level', sa.Integer(), nullable=False, server_default='1'),
        sa.ForeignKeyConstraint(['engagement_id'], ['engagements.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['skill_id'], ['skills.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('engagement_id', 'skill_id', name='uq_engagement_skill'),
    )
    op.create_index('ix_engagement_skills_engagement_id', 'engagement_skills', ['engagement_id'])
    op.create_index('ix_engagement_skills_skill_id', 'engagement_skills', ['skill_id'])


def downgrade() -> None:
    op.drop_table('engagement_skills')
    op.drop_table('user_skills')
    op.drop_table('skills')
    op.drop_table('skill_categories')
