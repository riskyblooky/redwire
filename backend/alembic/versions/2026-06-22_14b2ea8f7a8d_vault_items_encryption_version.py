"""vault_items.encryption_version

Revision ID: 14b2ea8f7a8d
Revises: f34670cca6d7
Create Date: 2026-06-22 22:44:19.296782+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '14b2ea8f7a8d'
down_revision: Union[str, None] = 'f34670cca6d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # GHSA-3r7j-7h5r-gxgx Issue 3 follow-up. Adds the tracking flag for
    # at-rest encryption state of FILE-type vault item MinIO blobs.
    #
    # New rows default to 1 (encrypted under the current Fernet scheme)
    # because the upload path has been calling encrypt_bytes() since
    # RDW-057. *Existing* rows with a file_path get flagged 0 — they
    # may or may not be encrypted (some shipped pre-RDW-057). The
    # startup backfill at backend/main.py iterates these on next boot,
    # sniffs the Fernet shape, encrypts if needed, and bumps the flag
    # to 1. Idempotent and skip-on-error so a stuck row doesn't block
    # the boot loop.
    op.add_column(
        'vault_items',
        sa.Column('encryption_version', sa.Integer(), server_default='1', nullable=False),
    )
    # Flag existing FILE rows as needing the legacy-blob check.
    op.execute(
        "UPDATE vault_items SET encryption_version = 0 WHERE file_path IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column('vault_items', 'encryption_version')
