"""add per-result host/port/password to spray_results

Revision ID: r9s0t1u2v3w4
Revises: q8r9s0t1u2v3
Create Date: 2026-04-29

The original spray schema only stored target_host and password on the
campaign. That works for single-host single-credential runs but loses
information when nxc is given a CIDR target or wordlist for users/passwords.

These columns are populated per-result by the parser so:
  - We can show "which host did this user/password hit" in the results table.
  - Auto-vault uses the per-result password rather than the campaign-level
    placeholder string ("[N passwords]").

All columns are nullable so existing rows remain valid.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic
revision = 'r9s0t1u2v3w4'
down_revision = 'q8r9s0t1u2v3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    cols = [c['name'] for c in inspector.get_columns('spray_results')]

    if 'target_host' not in cols:
        op.add_column('spray_results', sa.Column('target_host', sa.String(255), nullable=True))
    if 'target_port' not in cols:
        op.add_column('spray_results', sa.Column('target_port', sa.Integer(), nullable=True))
    if 'password' not in cols:
        op.add_column('spray_results', sa.Column('password', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('spray_results', 'password')
    op.drop_column('spray_results', 'target_port')
    op.drop_column('spray_results', 'target_host')
