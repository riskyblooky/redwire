from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ReportThemeCreate(BaseModel):
    name: str
    description: Optional[str] = None
    primary_color: str = "#4F46E5"
    secondary_color: str = "#7C3AED"
    header_text_color: str = "#1E293B"
    body_text_color: str = "#334155"
    table_header_bg: str = "#4F46E5"
    table_header_text: str = "#FFFFFF"
    font_family: str = "Helvetica"
    font_size_body: int = 10
    font_size_heading: int = 20
    logo_base64: Optional[str] = None
    logo_scale: Optional[int] = Field(None, ge=10, le=400)
    show_page_numbers: bool = True
    show_cover_page: bool = True
    cover_title: str = "Security Assessment Report"
    header_text: Optional[str] = None
    footer_text: Optional[str] = "CONFIDENTIAL"
    page_size: str = "letter"
    # Deepened controls (all optional; generator falls back to its defaults).
    severity_critical_color: Optional[str] = None
    severity_high_color: Optional[str] = None
    severity_medium_color: Optional[str] = None
    severity_low_color: Optional[str] = None
    severity_info_color: Optional[str] = None
    table_zebra_enabled: Optional[bool] = None
    table_alt_row_bg: Optional[str] = None
    table_grid_color: Optional[str] = None
    header_left: Optional[str] = None
    header_center: Optional[str] = None
    header_right: Optional[str] = None
    footer_left: Optional[str] = None
    footer_center: Optional[str] = None
    footer_right: Optional[str] = None
    show_page_x_of_y: Optional[bool] = None
    cover_template: Optional[str] = None
    cover_subtitle: Optional[str] = None
    cover_background_base64: Optional[str] = None
    report_reference: Optional[str] = None
    report_version: Optional[str] = None
    show_evidence_filenames: Optional[bool] = None
    show_finding_severity_bar: Optional[bool] = None
    show_section_title_background: Optional[bool] = None
    is_default: bool = False


class ReportThemeUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    header_text_color: Optional[str] = None
    body_text_color: Optional[str] = None
    table_header_bg: Optional[str] = None
    table_header_text: Optional[str] = None
    font_family: Optional[str] = None
    font_size_body: Optional[int] = None
    font_size_heading: Optional[int] = None
    logo_base64: Optional[str] = None
    logo_scale: Optional[int] = Field(None, ge=10, le=400)
    show_page_numbers: Optional[bool] = None
    show_cover_page: Optional[bool] = None
    cover_title: Optional[str] = None
    header_text: Optional[str] = None
    footer_text: Optional[str] = None
    page_size: Optional[str] = None
    severity_critical_color: Optional[str] = None
    severity_high_color: Optional[str] = None
    severity_medium_color: Optional[str] = None
    severity_low_color: Optional[str] = None
    severity_info_color: Optional[str] = None
    table_zebra_enabled: Optional[bool] = None
    table_alt_row_bg: Optional[str] = None
    table_grid_color: Optional[str] = None
    header_left: Optional[str] = None
    header_center: Optional[str] = None
    header_right: Optional[str] = None
    footer_left: Optional[str] = None
    footer_center: Optional[str] = None
    footer_right: Optional[str] = None
    show_page_x_of_y: Optional[bool] = None
    cover_template: Optional[str] = None
    cover_subtitle: Optional[str] = None
    cover_background_base64: Optional[str] = None
    report_reference: Optional[str] = None
    report_version: Optional[str] = None
    show_evidence_filenames: Optional[bool] = None
    show_finding_severity_bar: Optional[bool] = None
    show_section_title_background: Optional[bool] = None
    is_default: Optional[bool] = None


class ReportThemeResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    primary_color: str
    secondary_color: str
    header_text_color: str
    body_text_color: str
    table_header_bg: str
    table_header_text: str
    font_family: str
    font_size_body: int
    font_size_heading: int
    logo_base64: Optional[str] = None
    logo_scale: Optional[int] = None
    show_page_numbers: bool
    show_cover_page: bool
    cover_title: str
    header_text: Optional[str] = None
    footer_text: Optional[str] = None
    page_size: str
    severity_critical_color: Optional[str] = None
    severity_high_color: Optional[str] = None
    severity_medium_color: Optional[str] = None
    severity_low_color: Optional[str] = None
    severity_info_color: Optional[str] = None
    table_zebra_enabled: Optional[bool] = None
    table_alt_row_bg: Optional[str] = None
    table_grid_color: Optional[str] = None
    header_left: Optional[str] = None
    header_center: Optional[str] = None
    header_right: Optional[str] = None
    footer_left: Optional[str] = None
    footer_center: Optional[str] = None
    footer_right: Optional[str] = None
    show_page_x_of_y: Optional[bool] = None
    cover_template: Optional[str] = None
    cover_subtitle: Optional[str] = None
    cover_background_base64: Optional[str] = None
    report_reference: Optional[str] = None
    report_version: Optional[str] = None
    show_evidence_filenames: Optional[bool] = None
    show_finding_severity_bar: Optional[bool] = None
    show_section_title_background: Optional[bool] = None
    is_default: bool
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str] = None
    updated_by: Optional[str] = None

    class Config:
        from_attributes = True
