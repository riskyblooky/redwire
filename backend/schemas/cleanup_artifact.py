from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from models.cleanup_artifact import CleanupArtifactStatus
from schemas._field_limits import (
    ENUM_STR,
    LONG_TEXT,
    SHORT_LABEL,
    TITLE,
    UUID_FIELD,
)


class LinkedFindingSummary(BaseModel):
    id: str
    title: str
    severity: str

    class Config:
        from_attributes = True


class LinkedTestCaseSummary(BaseModel):
    id: str
    title: str

    class Config:
        from_attributes = True


class LinkedAssetSummary(BaseModel):
    id: str
    name: str
    identifier: str

    class Config:
        from_attributes = True


class CleanupArtifactBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=TITLE)
    artifact_type: str = Field(..., max_length=SHORT_LABEL)
    status: Optional[CleanupArtifactStatus] = CleanupArtifactStatus.PENDING
    location: Optional[str] = Field(None, max_length=TITLE)
    description: Optional[str] = Field(None, max_length=LONG_TEXT)
    cleanup_notes: Optional[str] = Field(None, max_length=LONG_TEXT)
    classification_level: Optional[str] = Field(None, max_length=ENUM_STR)
    classification_suffix: Optional[str] = Field(None, max_length=SHORT_LABEL)


class CleanupArtifactCreate(CleanupArtifactBase):
    engagement_id: str = Field(..., max_length=UUID_FIELD)


class CleanupArtifactUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=TITLE)
    artifact_type: Optional[str] = Field(None, max_length=SHORT_LABEL)
    status: Optional[CleanupArtifactStatus] = None
    location: Optional[str] = Field(None, max_length=TITLE)
    description: Optional[str] = Field(None, max_length=LONG_TEXT)
    cleanup_notes: Optional[str] = Field(None, max_length=LONG_TEXT)
    classification_level: Optional[str] = Field(None, max_length=ENUM_STR)
    classification_suffix: Optional[str] = Field(None, max_length=SHORT_LABEL)


class CleanupArtifactResponse(CleanupArtifactBase):
    id: str
    engagement_id: str
    cleaned_at: Optional[datetime] = None
    cleaned_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    created_by: str
    updated_by: Optional[str] = None
    created_by_username: Optional[str] = None
    created_by_profile_photo: Optional[str] = None
    cleaned_by_username: Optional[str] = None
    findings: List[LinkedFindingSummary] = []
    testcases: List[LinkedTestCaseSummary] = []
    assets: List[LinkedAssetSummary] = []

    class Config:
        from_attributes = True

