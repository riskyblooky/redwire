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

    # Logo (base64 data URI, optional)
    logo_base64 = Column(Text, nullable=True)

    # Page layout
    show_page_numbers = Column(Boolean, nullable=False, default=True)
    show_cover_page = Column(Boolean, nullable=False, default=True)
    cover_title = Column(String(500), nullable=False, default="Security Assessment Report")
    header_text = Column(String(500), nullable=True)
    footer_text = Column(String(500), nullable=True, default="CONFIDENTIAL")
    page_size = Column(String(10), nullable=False, default="letter")

    is_default = Column(Boolean, nullable=False, default=False)
