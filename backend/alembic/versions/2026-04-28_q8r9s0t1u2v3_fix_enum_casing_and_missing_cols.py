"""fix enum casing and add missing engagement columns

Revision ID: q8r9s0t1u2v3
Revises: p7q8r9s0t1u2
Create Date: 2026-04-28

Fixes:
- Rename enum values from lowercase to uppercase to match SQLAlchemy model names
- Add missing 'scope' and 'objectives' columns to engagements table
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic
revision = 'q8r9s0t1u2v3'
down_revision = 'p7q8r9s0t1u2'
branch_labels = None
depends_on = None


def _get_enum_values(bind, enum_name):
    """Get current values of a PostgreSQL enum type."""
    result = bind.execute(
        sa.text("SELECT enumlabel FROM pg_enum JOIN pg_type ON pg_enum.enumtypid = pg_type.oid WHERE pg_type.typname = :name"),
        {"name": enum_name}
    )
    return {row[0] for row in result}


def _rename_enum_values(bind, enum_name, renames):
    """Rename enum values only if old value exists (idempotent)."""
    current = _get_enum_values(bind, enum_name)
    for old, new in renames:
        if old in current and new not in current:
            op.execute(f"ALTER TYPE {enum_name} RENAME VALUE '{old}' TO '{new}'")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # ── Fix enum casing: userrole ──
    _rename_enum_values(bind, 'userrole', [
        ('admin', 'ADMIN'),
        ('team_lead', 'TEAM_LEAD'),
        ('operator', 'OPERATOR'),
        ('read_only', 'READ_ONLY'),
    ])

    # ── Fix enum casing: engagementstatus ──
    _rename_enum_values(bind, 'engagementstatus', [
        ('planning', 'PLANNING'),
        ('in_progress', 'IN_PROGRESS'),
        ('reporting', 'REPORTING'),
        ('completed', 'COMPLETED'),
        ('on_hold', 'ON_HOLD'),
    ])

    # ── Fix enum casing: severity ──
    _rename_enum_values(bind, 'severity', [
        ('critical', 'CRITICAL'),
        ('high', 'HIGH'),
        ('medium', 'MEDIUM'),
        ('low', 'LOW'),
        ('info', 'INFO'),
    ])

    # ── Fix enum casing: findingstatus ──
    _rename_enum_values(bind, 'findingstatus', [
        ('open', 'OPEN'),
        ('in_review', 'IN_REVIEW'),
        ('verified', 'VERIFIED'),
        ('closed', 'CLOSED'),
        ('false_positive', 'FALSE_POSITIVE'),
    ])

    # ── Fix enum casing: testcasecategory ──
    _rename_enum_values(bind, 'testcasecategory', [
        ('reconnaissance', 'RECONNAISSANCE'),
        ('scanning', 'SCANNING'),
        ('exploitation', 'EXPLOITATION'),
        ('post_exploitation', 'POST_EXPLOITATION'),
        ('privilege_escalation', 'PRIVILEGE_ESCALATION'),
        ('persistence', 'PERSISTENCE'),
        ('lateral_movement', 'LATERAL_MOVEMENT'),
        ('web_application', 'WEB_APPLICATION'),
        ('social_engineering', 'SOCIAL_ENGINEERING'),
        ('physical', 'PHYSICAL'),
        ('other', 'OTHER'),
    ])

    # ── Add missing engagement columns ──
    eng_columns = [c['name'] for c in inspector.get_columns('engagements')]

    if 'scope' not in eng_columns:
        op.add_column('engagements', sa.Column('scope', sa.Text(), nullable=True))
    if 'objectives' not in eng_columns:
        op.add_column('engagements', sa.Column('objectives', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('engagements', 'objectives')
    op.drop_column('engagements', 'scope')

    # Reverse enum renames would go here but is impractical
