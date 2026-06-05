from sqlalchemy import Column, String, Text, Boolean, JSON, Enum as SAEnum
from database import Base, AuditMixin
import uuid
import enum


class MarkingScheme(str, enum.Enum):
    """Which classification idiom a profile renders in.

    TLP_2_0 — FIRST.org Traffic Light Protocol 2.0 (RED/AMBER+STRICT/AMBER/
        GREEN/CLEAR). Banner is a right-justified header line.
    IC_DOD  — US IC/DoD base ladder (U/C/S/TS). Banner is centered top *and*
        bottom of every page; portions carry parenthetical marks like (S).
    CUSTOM  — operator-defined ordered levels; rendered IC-style by default.
    """
    TLP_2_0 = "TLP_2_0"
    IC_DOD = "IC_DOD"
    CUSTOM = "CUSTOM"


class MarkingEnforcement(str, enum.Enum):
    """How strict the pre-generation marking lint is.

    OFF   — no checks.
    WARN  — flag portions still riding the inherited default (review aid).
    BLOCK — refuse to generate if any portion has no *effective* mark.
    """
    OFF = "OFF"
    WARN = "WARN"
    BLOCK = "BLOCK"


class MarkingProfile(Base, AuditMixin):
    """A reusable classification/marking policy, orthogonal to ReportTheme
    (looks) and ReportLayout (content). Selected per engagement/report.

    `levels` is the single source of truth for the ladder. Each entry:
        {
          "abbreviation": "S",          # the token rendered, e.g. (S) / TLP:RED
          "full_name":    "SECRET",     # legend / banner long form
          "rank":         3,            # higher = more sensitive; drives roll-up
          "banner_color": "#C8102E",    # banner fill for this level
          "text_color":   "#FFFFFF"     # banner text color
        }
    Only `rank` participates in roll-up; the free-text portion suffix
    (classification_suffix on each entity) is carried along but never ranked.
    """
    __tablename__ = "marking_profiles"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)

    scheme = Column(
        SAEnum(MarkingScheme, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        default=MarkingScheme.IC_DOD,
    )

    # Ordered list of level dicts (see class docstring).
    levels = Column(JSON, nullable=False, default=list)

    enforcement = Column(
        SAEnum(MarkingEnforcement, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        default=MarkingEnforcement.WARN,
    )

    # Where the rolled-up mark is drawn on each image / table. Lists of anchor
    # tokens: TOP_LEFT TOP_CENTER TOP_RIGHT BOTTOM_LEFT BOTTOM_CENTER
    # BOTTOM_RIGHT CAPTION. Empty list = no mark on that object type.
    image_mark_anchors = Column(JSON, nullable=False, default=lambda: ["CAPTION"])
    table_mark_anchors = Column(JSON, nullable=False, default=lambda: ["CAPTION"])

    # Render inline portion marks (heading/title prefixes, finding/table/row/
    # image marks). When False, only the page banner (+ cover legend) renders —
    # the TLP idiom is typically banner-only. Null → True.
    inline_portion_marks = Column(Boolean, nullable=True)

    # Per-row marks inside tables when rows differ in level (separate from the
    # table-level corner/caption mark above — both may be on at once).
    table_per_row_marks = Column(Boolean, nullable=False, default=False)

    # Overprint the mark onto the image bitmap so a detached screenshot stays
    # marked, in addition to the anchor text drawn around it.
    stamp_images = Column(Boolean, nullable=False, default=False)

    # How static/structural headings (TOC, "Severity Distribution", section
    # titles with no explicit mark) are marked: "LOWEST" (the lowest level,
    # e.g. (U)/TLP:CLEAR) or "INHERIT" (the engagement default). Null → LOWEST.
    static_heading_marks = Column(String(20), nullable=True)

    # Render a classification legend block (TLP definitions / IC ladder) on the
    # cover, and the IC distribution statement when set.
    show_legend = Column(Boolean, nullable=False, default=True)
    distribution_statement = Column(Text, nullable=True)

    is_default = Column(Boolean, nullable=False, default=False)
    # Seeded TLP 2.0 / IC built-ins are immutable (the router blocks edits).
    is_builtin = Column(Boolean, nullable=False, default=False)
