from pydantic import BaseModel
from typing import List, Optional
from enum import Enum


class ReportFormat(str, Enum):
    PDF = "pdf"
    MARKDOWN = "markdown"
    JSON_ZIP = "json_zip"


class ReportConfiguration(BaseModel):
    engagement_id: str
    layout_id: str
    report_format: ReportFormat = ReportFormat.PDF
    exclude_severities: List[str] = []
    theme_id: Optional[str] = None
    include_evidence: bool = True
    finding_ids: Optional[List[str]] = None      # None = all, [] = none, [...] = specific
    testcase_ids: Optional[List[str]] = None
    cleanup_ids: Optional[List[str]] = None
