from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from schemas._field_limits import (
    DESCRIPTION,
    ENUM_STR,
    HEX_COLOR,
    JSON_BLOB,
    NAME,
    SHORT_LABEL,
    TITLE,
)


class ReportThemeCreate(BaseModel):
    name: str = Field(..., max_length=NAME)
    description: Optional[str] = Field(None, max_length=DESCRIPTION)
    primary_color: str = Field("#4F46E5", max_length=HEX_COLOR)
    secondary_color: str = Field("#7C3AED", max_length=HEX_COLOR)
    header_text_color: str = Field("#1E293B", max_length=HEX_COLOR)
    body_text_color: str = Field("#334155", max_length=HEX_COLOR)
    table_header_bg: str = Field("#4F46E5", max_length=HEX_COLOR)
    table_header_text: str = Field("#FFFFFF", max_length=HEX_COLOR)
    font_family: str = Field("Helvetica", max_length=SHORT_LABEL)
    font_size_body: int = 10
    font_size_heading: int = 20
    logo_base64: Optional[str] = Field(None, max_length=JSON_BLOB)
    logo_scale: Optional[int] = Field(None, ge=10, le=400)
    show_page_numbers: bool = True
    show_cover_page: bool = True
    cover_title: str = Field("Security Assessment Report", max_length=TITLE)
    header_text: Optional[str] = Field(None, max_length=TITLE)
    footer_text: Optional[str] = Field("CONFIDENTIAL", max_length=TITLE)
    page_size: str = Field("letter", max_length=ENUM_STR)
    # Deepened controls (all optional; generator falls back to its defaults).
    severity_critical_color: Optional[str] = Field(None, max_length=HEX_COLOR)
    severity_high_color: Optional[str] = Field(None, max_length=HEX_COLOR)
    severity_medium_color: Optional[str] = Field(None, max_length=HEX_COLOR)
    severity_low_color: Optional[str] = Field(None, max_length=HEX_COLOR)
    severity_info_color: Optional[str] = Field(None, max_length=HEX_COLOR)
    table_zebra_enabled: Optional[bool] = None
    table_alt_row_bg: Optional[str] = Field(None, max_length=HEX_COLOR)
    table_grid_color: Optional[str] = Field(None, max_length=HEX_COLOR)
    header_left: Optional[str] = Field(None, max_length=TITLE)
    header_center: Optional[str] = Field(None, max_length=TITLE)
    header_right: Optional[str] = Field(None, max_length=TITLE)
    footer_left: Optional[str] = Field(None, max_length=TITLE)
    footer_center: Optional[str] = Field(None, max_length=TITLE)
    footer_right: Optional[str] = Field(None, max_length=TITLE)
    show_page_x_of_y: Optional[bool] = None
    cover_template: Optional[str] = Field(None, max_length=ENUM_STR)
    cover_subtitle: Optional[str] = Field(None, max_length=TITLE)
    cover_background_base64: Optional[str] = Field(None, max_length=JSON_BLOB)
    report_reference: Optional[str] = Field(None, max_length=SHORT_LABEL)
    report_version: Optional[str] = Field(None, max_length=SHORT_LABEL)
    show_evidence_filenames: Optional[bool] = None
    show_finding_severity_bar: Optional[bool] = None
    show_section_title_background: Optional[bool] = None
    is_default: bool = False


class ReportThemeUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=NAME)
    description: Optional[str] = Field(None, max_length=DESCRIPTION)
    primary_color: Optional[str] = Field(None, max_length=HEX_COLOR)
    secondary_color: Optional[str] = Field(None, max_length=HEX_COLOR)
    header_text_color: Optional[str] = Field(None, max_length=HEX_COLOR)
    body_text_color: Optional[str] = Field(None, max_length=HEX_COLOR)
    table_header_bg: Optional[str] = Field(None, max_length=HEX_COLOR)
    table_header_text: Optional[str] = Field(None, max_length=HEX_COLOR)
    font_family: Optional[str] = Field(None, max_length=SHORT_LABEL)
    font_size_body: Optional[int] = None
    font_size_heading: Optional[int] = None
    logo_base64: Optional[str] = Field(None, max_length=JSON_BLOB)
    logo_scale: Optional[int] = Field(None, ge=10, le=400)
    show_page_numbers: Optional[bool] = None
    show_cover_page: Optional[bool] = None
    cover_title: Optional[str] = Field(None, max_length=TITLE)
    header_text: Optional[str] = Field(None, max_length=TITLE)
    footer_text: Optional[str] = Field(None, max_length=TITLE)
    page_size: Optional[str] = Field(None, max_length=ENUM_STR)
    severity_critical_color: Optional[str] = Field(None, max_length=HEX_COLOR)
    severity_high_color: Optional[str] = Field(None, max_length=HEX_COLOR)
    severity_medium_color: Optional[str] = Field(None, max_length=HEX_COLOR)
    severity_low_color: Optional[str] = Field(None, max_length=HEX_COLOR)
    severity_info_color: Optional[str] = Field(None, max_length=HEX_COLOR)
    table_zebra_enabled: Optional[bool] = None
    table_alt_row_bg: Optional[str] = Field(None, max_length=HEX_COLOR)
    table_grid_color: Optional[str] = Field(None, max_length=HEX_COLOR)
    header_left: Optional[str] = Field(None, max_length=TITLE)
    header_center: Optional[str] = Field(None, max_length=TITLE)
    header_right: Optional[str] = Field(None, max_length=TITLE)
    footer_left: Optional[str] = Field(None, max_length=TITLE)
    footer_center: Optional[str] = Field(None, max_length=TITLE)
    footer_right: Optional[str] = Field(None, max_length=TITLE)
    show_page_x_of_y: Optional[bool] = None
    cover_template: Optional[str] = Field(None, max_length=ENUM_STR)
    cover_subtitle: Optional[str] = Field(None, max_length=TITLE)
    cover_background_base64: Optional[str] = Field(None, max_length=JSON_BLOB)
    report_reference: Optional[str] = Field(None, max_length=SHORT_LABEL)
    report_version: Optional[str] = Field(None, max_length=SHORT_LABEL)
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
