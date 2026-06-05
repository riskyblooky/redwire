from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from schemas.finding import TagResponse
from schemas.evidence import EvidenceResponse

class TestCaseBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    category: str
    description: str
    steps: Optional[str] = None
    expected_result: Optional[str] = None
    actual_result: Optional[str] = None
    is_executed: Optional[bool] = False
    is_successful: Optional[bool] = None
    notes: Optional[str] = None
    classification_level: Optional[str] = Field(None, max_length=20)
    classification_suffix: Optional[str] = Field(None, max_length=120)

class TestCaseCreate(TestCaseBase):
    engagement_id: str
    parent_id: Optional[str] = None
    tag_ids: list[str] = []
    attack_technique_ids: list[str] = []

class TestCaseUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    category: Optional[str] = None
    description: Optional[str] = None
    engagement_id: Optional[str] = None
    parent_id: Optional[str] = None
    steps: Optional[str] = None
    expected_result: Optional[str] = None
    actual_result: Optional[str] = None
    is_executed: Optional[bool] = None
    is_successful: Optional[bool] = None
    notes: Optional[str] = None
    classification_level: Optional[str] = Field(None, max_length=20)
    classification_suffix: Optional[str] = Field(None, max_length=120)
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
