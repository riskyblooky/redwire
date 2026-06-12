from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from schemas._field_limits import DESCRIPTION, ENUM_STR, NAME, SHORT_LABEL, UUID_FIELD

class EvidenceBase(BaseModel):
    original_filename: str = Field(..., max_length=NAME)
    description: Optional[str] = Field(None, max_length=DESCRIPTION)
    include_in_report: Optional[bool] = True
    classification_level: Optional[str] = Field(None, max_length=ENUM_STR)
    classification_suffix: Optional[str] = Field(None, max_length=SHORT_LABEL)

class EvidenceCreate(EvidenceBase):
    finding_id: Optional[str] = Field(None, max_length=UUID_FIELD)
    testcase_id: Optional[str] = Field(None, max_length=UUID_FIELD)
    engagement_id: Optional[str] = Field(None, max_length=UUID_FIELD)

class EvidenceResponse(EvidenceBase):
    id: str
    finding_id: Optional[str] = None
    testcase_id: Optional[str] = None
    engagement_id: Optional[str] = None
    filename: str
    file_path: str
    file_size: int
    mime_type: Optional[str]
    created_at: datetime
    updated_at: datetime
    created_by: str
    created_by_username: Optional[str] = None
    created_by_profile_photo: Optional[str] = None
    updated_by: Optional[str] = None
    unresolved_thread_count: Optional[int] = 0
    finding_title: Optional[str] = None
    testcase_title: Optional[str] = None

    class Config:
        from_attributes = True
