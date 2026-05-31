"""add totp_last_timestep to users

Revision ID: 9c78e930ca21
Revises: ba445837760a
Create Date: 2026-05-31 21:33:29.486383+00:00

Adds a per-user TOTP replay marker (GHSA-xqfh-2j9p-vmff). The verifier
records the last successfully consumed time-step here and rejects any
code whose matched step is <= this value, enforcing the one-time
property of RFC 6238.

Nullable, no default — existing users get NULL, which the verifier
treats as "no prior step" so their next 2FA prompt proceeds normally.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '9c78e930ca21'
down_revision: Union[str, None] = 'ba445837760a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('totp_last_timestep', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'totp_last_timestep')
