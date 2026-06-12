from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from enum import Enum
from schemas._field_limits import (
    DESCRIPTION,
    ENUM_STR,
    LONG_TEXT,
    NAME,
    SHORT_LABEL,
    TITLE,
)


class SectionType(str, Enum):
    TEXT = "text"
    FINDINGS = "findings"
    TESTCASES = "testcases"
    CLEANUP_ARTIFACTS = "cleanup_artifacts"


# ── Report Section schemas ──

class ReportSectionBase(BaseModel):
    section_type: SectionType = SectionType.TEXT
    title: str = Field(..., max_length=TITLE)
    content: Optional[str] = Field("", max_length=LONG_TEXT)
    sort_order: int = 0
    classification_level: Optional[str] = Field(None, max_length=ENUM_STR)
    classification_suffix: Optional[str] = Field(None, max_length=SHORT_LABEL)
    page_break_before: Optional[bool] = False


class ReportSectionCreate(ReportSectionBase):
    pass


class ReportSectionResponse(ReportSectionBase):
    id: str

    class Config:
        from_attributes = True


# ── Report Layout schemas (engagement-scoped) ──

class ReportLayoutCreate(BaseModel):
    name: str = Field(..., max_length=NAME)
    is_default: bool = False
    sections: List[ReportSectionCreate] = []


class ReportLayoutUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=NAME)
    is_default: Optional[bool] = None
    sections: Optional[List[ReportSectionCreate]] = None


class ReportLayoutResponse(BaseModel):
    id: str
    name: str
    engagement_id: str
    is_default: bool
    sections: List[ReportSectionResponse] = []
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str] = None
    updated_by: Optional[str] = None

    class Config:
        from_attributes = True


# ── Report Layout Template schemas (global) ──

class ReportLayoutTemplateSectionCreate(ReportSectionBase):
    pass


class ReportLayoutTemplateSectionResponse(ReportSectionBase):
    id: str

    class Config:
        from_attributes = True


class ReportLayoutTemplateCreate(BaseModel):
    name: str = Field(..., max_length=NAME)
    description: Optional[str] = Field(None, max_length=DESCRIPTION)
    sections: List[ReportLayoutTemplateSectionCreate] = []


class ReportLayoutTemplateUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=NAME)
    description: Optional[str] = Field(None, max_length=DESCRIPTION)
    sections: Optional[List[ReportLayoutTemplateSectionCreate]] = None


class ReportLayoutTemplateResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    sections: List[ReportLayoutTemplateSectionResponse] = []
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str] = None
    updated_by: Optional[str] = None

    class Config:
        from_attributes = True
