"""add_marking_profiles_and_classification

Revision ID: 293665bb09ce
Revises: 9c78e930ca21
Create Date: 2026-06-04 00:10:36.322259+00:00

Adds the marking_profiles table, classification columns on the markable
entities (finding / evidence / testcase / cleanup_artifact / report_section),
and the engagement-level marking default + ceiling + profile FK. Seeds the two
built-in profiles (TLP 2.0, IC/DoD base ladder).

Note: autogenerate also surfaced unrelated pre-existing drift on spray_*,
*_attack_techniques and markdown_images (NOT NULL / index / FK churn). That
drift is intentionally NOT included here — it belongs in its own cleanup
migration so this one stays scoped to the marking feature.
"""
from typing import Sequence, Union
from datetime import datetime
import uuid

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '293665bb09ce'
down_revision: Union[str, None] = '9c78e930ca21'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Lightweight table construct for seeding. scheme/enforcement are declared as
# String here (not the PG enum) — psycopg coerces the text to the enum type on
# insert, which avoids depending on the SQLAlchemy enum object at migration time.
_seed_table = sa.table(
    'marking_profiles',
    sa.column('id', sa.String),
    sa.column('name', sa.String),
    sa.column('description', sa.Text),
    sa.column('scheme', sa.String),
    sa.column('levels', sa.JSON),
    sa.column('enforcement', sa.String),
    sa.column('image_mark_anchors', sa.JSON),
    sa.column('table_mark_anchors', sa.JSON),
    sa.column('table_per_row_marks', sa.Boolean),
    sa.column('stamp_images', sa.Boolean),
    sa.column('show_legend', sa.Boolean),
    sa.column('distribution_statement', sa.Text),
    sa.column('is_default', sa.Boolean),
    sa.column('is_builtin', sa.Boolean),
    sa.column('created_at', sa.DateTime),
    sa.column('updated_at', sa.DateTime),
)


def _builtin_rows():
    now = datetime.utcnow()
    return [
        {
            'id': str(uuid.uuid4()),
            'name': 'TLP 2.0',
            'description': 'FIRST.org Traffic Light Protocol 2.0. Banner is a right-justified header line.',
            'scheme': 'TLP_2_0',
            'levels': [
                {'abbreviation': 'CLEAR',        'full_name': 'TLP:CLEAR',        'rank': 1, 'banner_color': '#FFFFFF', 'text_color': '#000000'},
                {'abbreviation': 'GREEN',        'full_name': 'TLP:GREEN',        'rank': 2, 'banner_color': '#33FF00', 'text_color': '#000000'},
                {'abbreviation': 'AMBER',        'full_name': 'TLP:AMBER',        'rank': 3, 'banner_color': '#FFC000', 'text_color': '#000000'},
                {'abbreviation': 'AMBER+STRICT', 'full_name': 'TLP:AMBER+STRICT', 'rank': 4, 'banner_color': '#FFC000', 'text_color': '#000000'},
                {'abbreviation': 'RED',          'full_name': 'TLP:RED',          'rank': 5, 'banner_color': '#FF2B2B', 'text_color': '#000000'},
            ],
            'enforcement': 'WARN',
            'image_mark_anchors': ['CAPTION'],
            'table_mark_anchors': ['CAPTION'],
            'table_per_row_marks': False,
            'stamp_images': False,
            'show_legend': True,
            'distribution_statement': None,
            'is_default': True,
            'is_builtin': True,
            'created_at': now,
            'updated_at': now,
        },
        {
            'id': str(uuid.uuid4()),
            'name': 'IC / DoD (base ladder)',
            'description': 'US IC/DoD base ladder (U/C/S/TS). Centered banner top and bottom of every page; parenthetical portion marks. Add caveats via the per-portion free-text suffix.',
            'scheme': 'IC_DOD',
            'levels': [
                {'abbreviation': 'U',  'full_name': 'UNCLASSIFIED', 'rank': 1, 'banner_color': '#007A33', 'text_color': '#FFFFFF'},
                {'abbreviation': 'C',  'full_name': 'CONFIDENTIAL', 'rank': 2, 'banner_color': '#0033A0', 'text_color': '#FFFFFF'},
                {'abbreviation': 'S',  'full_name': 'SECRET',       'rank': 3, 'banner_color': '#C8102E', 'text_color': '#FFFFFF'},
                {'abbreviation': 'TS', 'full_name': 'TOP SECRET',   'rank': 4, 'banner_color': '#FF8C00', 'text_color': '#000000'},
            ],
            'enforcement': 'WARN',
            'image_mark_anchors': ['CAPTION'],
            'table_mark_anchors': ['CAPTION'],
            'table_per_row_marks': False,
            'stamp_images': False,
            'show_legend': True,
            'distribution_statement': None,
            'is_default': False,
            'is_builtin': True,
            'created_at': now,
            'updated_at': now,
        },
    ]


def upgrade() -> None:
    op.create_table(
        'marking_profiles',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('scheme', sa.Enum('TLP_2_0', 'IC_DOD', 'CUSTOM', name='markingscheme'), nullable=False),
        sa.Column('levels', sa.JSON(), nullable=False),
        sa.Column('enforcement', sa.Enum('OFF', 'WARN', 'BLOCK', name='markingenforcement'), nullable=False),
        sa.Column('image_mark_anchors', sa.JSON(), nullable=False),
        sa.Column('table_mark_anchors', sa.JSON(), nullable=False),
        sa.Column('table_per_row_marks', sa.Boolean(), nullable=False),
        sa.Column('stamp_images', sa.Boolean(), nullable=False),
        sa.Column('show_legend', sa.Boolean(), nullable=False),
        sa.Column('distribution_statement', sa.Text(), nullable=True),
        sa.Column('is_default', sa.Boolean(), nullable=False),
        sa.Column('is_builtin', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('updated_by', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_marking_profiles_name'), 'marking_profiles', ['name'], unique=False)

    # Classification columns on the markable entities (all nullable → inherit).
    op.add_column('findings', sa.Column('classification_level', sa.String(length=20), nullable=True))
    op.add_column('findings', sa.Column('classification_suffix', sa.String(length=120), nullable=True))
    op.add_column('evidence', sa.Column('classification_level', sa.String(length=20), nullable=True))
    op.add_column('evidence', sa.Column('classification_suffix', sa.String(length=120), nullable=True))
    op.add_column('testcases', sa.Column('classification_level', sa.String(length=20), nullable=True))
    op.add_column('testcases', sa.Column('classification_suffix', sa.String(length=120), nullable=True))
    op.add_column('cleanup_artifacts', sa.Column('classification_level', sa.String(length=20), nullable=True))
    op.add_column('cleanup_artifacts', sa.Column('classification_suffix', sa.String(length=120), nullable=True))
    op.add_column('report_sections', sa.Column('classification_level', sa.String(length=20), nullable=True))
    op.add_column('report_sections', sa.Column('classification_suffix', sa.String(length=120), nullable=True))

    # Engagement-level marking default + ceiling + profile FK.
    op.add_column('engagements', sa.Column('marking_profile_id', sa.String(), nullable=True))
    op.add_column('engagements', sa.Column('default_classification_level', sa.String(length=20), nullable=True))
    op.add_column('engagements', sa.Column('default_classification_suffix', sa.String(length=120), nullable=True))
    op.add_column('engagements', sa.Column('ceiling_classification_level', sa.String(length=20), nullable=True))
    op.create_index(op.f('ix_engagements_marking_profile_id'), 'engagements', ['marking_profile_id'], unique=False)
    op.create_foreign_key(
        'fk_engagements_marking_profile_id', 'engagements', 'marking_profiles',
        ['marking_profile_id'], ['id'], ondelete='SET NULL',
    )

    # Seed the built-in profiles.
    op.bulk_insert(_seed_table, _builtin_rows())


def downgrade() -> None:
    op.drop_constraint('fk_engagements_marking_profile_id', 'engagements', type_='foreignkey')
    op.drop_index(op.f('ix_engagements_marking_profile_id'), table_name='engagements')
    op.drop_column('engagements', 'ceiling_classification_level')
    op.drop_column('engagements', 'default_classification_suffix')
    op.drop_column('engagements', 'default_classification_level')
    op.drop_column('engagements', 'marking_profile_id')

    op.drop_column('report_sections', 'classification_suffix')
    op.drop_column('report_sections', 'classification_level')
    op.drop_column('cleanup_artifacts', 'classification_suffix')
    op.drop_column('cleanup_artifacts', 'classification_level')
    op.drop_column('testcases', 'classification_suffix')
    op.drop_column('testcases', 'classification_level')
    op.drop_column('evidence', 'classification_suffix')
    op.drop_column('evidence', 'classification_level')
    op.drop_column('findings', 'classification_suffix')
    op.drop_column('findings', 'classification_level')

    op.drop_index(op.f('ix_marking_profiles_name'), table_name='marking_profiles')
    op.drop_table('marking_profiles')

    # create_table auto-created these PG enum types; drop_table doesn't remove them.
    bind = op.get_bind()
    sa.Enum(name='markingscheme').drop(bind, checkfirst=True)
    sa.Enum(name='markingenforcement').drop(bind, checkfirst=True)
