from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from schemas.finding import TagResponse
from schemas.evidence import EvidenceResponse
from schemas._field_limits import (
    ENUM_STR,
    LONG_TEXT,
    SHORT_LABEL,
    TITLE,
    UUID_FIELD,
)

class TestCaseBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=TITLE)
    category: str = Field(..., max_length=SHORT_LABEL)
    description: str = Field(..., max_length=LONG_TEXT)
    steps: Optional[str] = Field(None, max_length=LONG_TEXT)
    expected_result: Optional[str] = Field(None, max_length=LONG_TEXT)
    actual_result: Optional[str] = Field(None, max_length=LONG_TEXT)
    is_executed: Optional[bool] = False
    is_successful: Optional[bool] = None
    notes: Optional[str] = Field(None, max_length=LONG_TEXT)
    classification_level: Optional[str] = Field(None, max_length=ENUM_STR)
    classification_suffix: Optional[str] = Field(None, max_length=SHORT_LABEL)

class TestCaseCreate(TestCaseBase):
    engagement_id: str = Field(..., max_length=UUID_FIELD)
    parent_id: Optional[str] = Field(None, max_length=UUID_FIELD)
    tag_ids: list[str] = []
    attack_technique_ids: list[str] = []

class TestCaseUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=TITLE)
    category: Optional[str] = Field(None, max_length=SHORT_LABEL)
    description: Optional[str] = Field(None, max_length=LONG_TEXT)
    engagement_id: Optional[str] = Field(None, max_length=UUID_FIELD)
    parent_id: Optional[str] = Field(None, max_length=UUID_FIELD)
    steps: Optional[str] = Field(None, max_length=LONG_TEXT)
    expected_result: Optional[str] = Field(None, max_length=LONG_TEXT)
    actual_result: Optional[str] = Field(None, max_length=LONG_TEXT)
    is_executed: Optional[bool] = None
    is_successful: Optional[bool] = None
    notes: Optional[str] = Field(None, max_length=LONG_TEXT)
    classification_level: Optional[str] = Field(None, max_length=ENUM_STR)
    classification_suffix: Optional[str] = Field(None, max_length=SHORT_LABEL)
    tag_ids: Optional[list[str]] = None
    attack_technique_ids: Optional[list[str]] = None

class LinkedFindingResponse(BaseModel):
    id: str
    title: str
    severity: str

    class Config:
        from_attributes = True

class LinkedVaultItemResponse(BaseModel):
    id: str
    name: str
    item_type: str

    class Config:
        from_attributes = True

class LinkedCleanupArtifactResponse(BaseModel):
    id: str
    title: str
    artifact_type: str
    status: str

    class Config:
        from_attributes = True

class LinkedPortResponse(BaseModel):
    id: str
    port_number: int
    protocol: str
    service_name: Optional[str] = None
    state: str

    class Config:
        from_attributes = True

class LinkedAssetResponse(BaseModel):
    id: str
    name: str
    asset_type: str
    identifier: str
    port_ids: Optional[list[str]] = None
    linked_ports: list[LinkedPortResponse] = []

    class Config:
        from_attributes = True


class TestCaseResponse(TestCaseBase):
    id: str
    engagement_id: str
    parent_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    created_by: str
    updated_by: Optional[str] = None
    created_by_username: Optional[str] = None
    created_by_profile_photo: Optional[str] = None
    unresolved_thread_count: int = 0
    findings: list[LinkedFindingResponse] = []
    vault_items: list[LinkedVaultItemResponse] = []
    assets: list[LinkedAssetResponse] = []
    cleanup_artifacts: list[LinkedCleanupArtifactResponse] = []
    evidence: list[EvidenceResponse] = []
    tags: list[TagResponse] = []
    attack_technique_ids: list[str] = []

    class Config:
        from_attributes = True
