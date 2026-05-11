from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from models.cleanup_artifact import CleanupArtifactStatus


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
    title: str = Field(..., min_length=1, max_length=500)
    artifact_type: str
    status: Optional[CleanupArtifactStatus] = CleanupArtifactStatus.PENDING
    location: Optional[str] = Field(None, max_length=500)
    description: Optional[str] = None
    cleanup_notes: Optional[str] = None


class CleanupArtifactCreate(CleanupArtifactBase):
    engagement_id: str


class CleanupArtifactUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    artifact_type: Optional[str] = None
    status: Optional[CleanupArtifactStatus] = None
    location: Optional[str] = Field(None, max_length=500)
    description: Optional[str] = None
    cleanup_notes: Optional[str] = None


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

