from pydantic import BaseModel
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
    show_page_numbers: bool = True
    show_cover_page: bool = True
    cover_title: str = "Security Assessment Report"
    header_text: Optional[str] = None
    footer_text: Optional[str] = "CONFIDENTIAL"
    page_size: str = "letter"
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
    show_page_numbers: Optional[bool] = None
    show_cover_page: Optional[bool] = None
    cover_title: Optional[str] = None
    header_text: Optional[str] = None
    footer_text: Optional[str] = None
    page_size: Optional[str] = None
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
    show_page_numbers: bool
    show_cover_page: bool
    cover_title: str
    header_text: Optional[str] = None
    footer_text: Optional[str] = None
    page_size: str
    is_default: bool
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str] = None
    updated_by: Optional[str] = None

    class Config:
        from_attributes = True
