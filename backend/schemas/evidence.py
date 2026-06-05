from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class EvidenceBase(BaseModel):
    original_filename: str
    description: Optional[str] = None
    include_in_report: Optional[bool] = True
    classification_level: Optional[str] = Field(None, max_length=20)
    classification_suffix: Optional[str] = Field(None, max_length=120)

class EvidenceCreate(EvidenceBase):
    finding_id: Optional[str] = None
    testcase_id: Optional[str] = None
    engagement_id: Optional[str] = None

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
