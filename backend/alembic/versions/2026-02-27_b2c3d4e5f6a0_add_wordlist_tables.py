"""add wordlist tables

Revision ID: b2c3d4e5f6a0
Revises: a1b2c3d4e5f9
Create Date: 2026-02-27 04:24:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a0'
down_revision: Union[str, None] = 'a1b2c3d4e5f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Wordlist metadata table
    op.create_table(
        'wordlist_meta',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('filename', sa.String(255), nullable=False),
        sa.Column('entry_count', sa.Integer(), default=0),
        sa.Column('status', sa.String(20), nullable=False, server_default='PROCESSING'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('uploaded_by', sa.String(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # Wordlist entries table (the rainbow table)
    op.create_table(
        'wordlist_entries',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('password', sa.Text(), nullable=False),
        sa.Column('ntlm', sa.String(32), nullable=True),
        sa.Column('md5', sa.String(32), nullable=True),
        sa.Column('sha1', sa.String(40), nullable=True),
        sa.Column('source', sa.String(255), nullable=True),
    )

    # Indexes for fast lookups
    op.create_index('ix_wordlist_entries_password', 'wordlist_entries', ['password'])
    op.create_index('ix_wordlist_entries_ntlm', 'wordlist_entries', ['ntlm'])
    op.create_index('ix_wordlist_entries_md5', 'wordlist_entries', ['md5'])
    op.create_index('ix_wordlist_entries_sha1', 'wordlist_entries', ['sha1'])
    op.create_index('ix_wordlist_entries_source', 'wordlist_entries', ['source'])


def downgrade() -> None:
    op.drop_table('wordlist_entries')
    op.drop_table('wordlist_meta')
