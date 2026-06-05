from sqlalchemy import Column, String, Text, Integer, Boolean
from database import Base, AuditMixin
import uuid


class ReportTheme(Base, AuditMixin):
    __tablename__ = "report_themes"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)

    # Colors (hex strings)
    primary_color = Column(String(9), nullable=False, default="#4F46E5")
    secondary_color = Column(String(9), nullable=False, default="#7C3AED")
    header_text_color = Column(String(9), nullable=False, default="#1E293B")
    body_text_color = Column(String(9), nullable=False, default="#334155")
    table_header_bg = Column(String(9), nullable=False, default="#4F46E5")
    table_header_text = Column(String(9), nullable=False, default="#FFFFFF")

    # Fonts
    font_family = Column(String(50), nullable=False, default="Helvetica")
    font_size_body = Column(Integer, nullable=False, default=10)
    font_size_heading = Column(Integer, nullable=False, default=20)

    # Logo (base64 data URI, optional). logo_scale is a percent (100 = default
    # height); aspect ratio is always preserved.
    logo_base64 = Column(Text, nullable=True)
    logo_scale = Column(Integer, nullable=True)

    # Page layout
    show_page_numbers = Column(Boolean, nullable=False, default=True)
    show_cover_page = Column(Boolean, nullable=False, default=True)
    cover_title = Column(String(500), nullable=False, default="Security Assessment Report")
    header_text = Column(String(500), nullable=True)
    footer_text = Column(String(500), nullable=True, default="CONFIDENTIAL")
    page_size = Column(String(10), nullable=False, default="letter")

    # ── Deepened controls (all nullable; the generator falls back to its
    # built-in _DEFAULTS when a column is null, so existing themes keep working).

    # Severity colors — promote the generator's hardcoded palette to the theme.
    severity_critical_color = Column(String(9), nullable=True)
    severity_high_color = Column(String(9), nullable=True)
    severity_medium_color = Column(String(9), nullable=True)
    severity_low_color = Column(String(9), nullable=True)
    severity_info_color = Column(String(9), nullable=True)

    # Table style tokens.
    table_zebra_enabled = Column(Boolean, nullable=True)
    table_alt_row_bg = Column(String(9), nullable=True)
    table_grid_color = Column(String(9), nullable=True)

    # Header / footer zones (left / center / right, top and bottom). When any
    # zone is set it supersedes the legacy header_text / footer_text strings.
    header_left = Column(String(255), nullable=True)
    header_center = Column(String(255), nullable=True)
    header_right = Column(String(255), nullable=True)
    footer_left = Column(String(255), nullable=True)
    footer_center = Column(String(255), nullable=True)
    footer_right = Column(String(255), nullable=True)
    show_page_x_of_y = Column(Boolean, nullable=True)

    # Cover.
    cover_template = Column(String(40), nullable=True)        # minimal | banded | full_bleed_image | classified
    cover_subtitle = Column(String(500), nullable=True)
    cover_background_base64 = Column(Text, nullable=True)
    report_reference = Column(String(120), nullable=True)
    report_version = Column(String(40), nullable=True)

    # Evidence
    show_evidence_filenames = Column(Boolean, nullable=True)

    # Finding card styling
    show_finding_severity_bar = Column(Boolean, nullable=True)      # colored left bar
    show_section_title_background = Column(Boolean, nullable=True)  # dark block behind section titles

    is_default = Column(Boolean, nullable=False, default=False)
