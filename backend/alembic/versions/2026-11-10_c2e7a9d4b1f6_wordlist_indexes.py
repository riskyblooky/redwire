"""wordlist_entries: drop the unused password index, index source

Revision ID: c2e7a9d4b1f6
Revises: b8d4f0a2c6e1
Create Date: 2026-11-10

Nothing looks wordlist entries up by plaintext password (cracking matches
on ntlm / md5 / sha1, and the bloom-filter load is a full streaming scan),
so ix_wordlist_entries_password was ~640 MB of write amplification on every
wordlist import. `source` — what deleting a wordlist (and the FK cascade
from wordlist_meta) filters on — had no index, so each delete was a
sequential scan of the whole table.

CONCURRENTLY, outside the transaction, as in b8d4f0a2c6e1; an INVALID
leftover from an interrupted build is dropped and rebuilt.
"""
from alembic import op
import sqlalchemy as sa


revision = "c2e7a9d4b1f6"
down_revision = "b8d4f0a2c6e1"
branch_labels = None
depends_on = None


def _build(bind, name, table, col):
    invalid = bind.execute(sa.text(
        "SELECT 1 FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
        "WHERE c.relname = :n AND NOT i.indisvalid"
    ), {"n": name}).scalar()
    if invalid:
        op.execute(f'DROP INDEX CONCURRENTLY IF EXISTS "{name}"')
    op.execute(f'CREATE INDEX CONCURRENTLY IF NOT EXISTS "{name}" ON "{table}" ("{col}")')


def upgrade():
    bind = op.get_bind()
    with op.get_context().autocommit_block():
        _build(bind, "ix_wordlist_entries_source", "wordlist_entries", "source")
        op.execute('DROP INDEX CONCURRENTLY IF EXISTS "ix_wordlist_entries_password"')


def downgrade():
    bind = op.get_bind()
    with op.get_context().autocommit_block():
        _build(bind, "ix_wordlist_entries_password", "wordlist_entries", "password")
        op.execute('DROP INDEX CONCURRENTLY IF EXISTS "ix_wordlist_entries_source"')
