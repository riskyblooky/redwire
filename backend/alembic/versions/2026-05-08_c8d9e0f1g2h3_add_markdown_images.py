"""Add markdown_images table

Tracks images uploaded inline via the markdown editor. Each row gates
access to a MinIO object via engagement-scoped permission checks.

Revision ID: c8d9e0f1g2h3
Revises: b7c8d9e0f1g2
Create Date: 2026-05-08
"""
from alembic import op
import sqlalchemy as sa


revision = 'c8d9e0f1g2h3'
down_revision = 'b7c8d9e0f1g2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'markdown_images',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('storage_key', sa.String(512), nullable=False),
        sa.Column('engagement_id', sa.String(), sa.ForeignKey('engagements.id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_by', sa.String(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('content_type', sa.String(100), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('original_filename', sa.String(255), nullable=True),
    )
    op.create_index('ix_markdown_images_engagement', 'markdown_images', ['engagement_id'])


def downgrade() -> None:
    op.drop_index('ix_markdown_images_engagement', table_name='markdown_images')
    op.drop_table('markdown_images')
