from pydantic import BaseModel
from typing import List, Optional
from enum import Enum


class ReportFormat(str, Enum):
    PDF = "pdf"
    MARKDOWN = "markdown"
    HTML = "html"
    JSON_ZIP = "json_zip"
    JSON_LAYOUT_ZIP = "json_layout_zip"


class ReportConfiguration(BaseModel):
    engagement_id: str
    layout_id: str
    report_format: ReportFormat = ReportFormat.PDF
    exclude_severities: List[str] = []
    theme_id: Optional[str] = None
    # Portion marking profile. None → fall back to the engagement's profile,
    # then the default profile, then no marking.
    marking_profile_id: Optional[str] = None
    include_evidence: bool = True
    finding_ids: Optional[List[str]] = None      # None = all, [] = none, [...] = specific
    testcase_ids: Optional[List[str]] = None
    cleanup_ids: Optional[List[str]] = None
