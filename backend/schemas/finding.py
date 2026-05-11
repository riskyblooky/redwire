from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from models.finding import Severity, FindingStatus
from models.template_status import TemplateStatus
from schemas.evidence import EvidenceResponse
from schemas.asset import AssetBase



class TagResponse(BaseModel):
    id: str
    name: str
    color: Optional[str] = None

    class Config:
        from_attributes = True

class LinkedTestCaseResponse(BaseModel):
    id: str
    title: str

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

class LinkedAssetResponse(AssetBase):
    id: str
    remediated: bool = False
    remediated_at: Optional[str] = None
    remediated_by: Optional[str] = None
    port_ids: Optional[List[str]] = None

    class Config:
        from_attributes = True

class FindingBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    category: Optional[str] = Field(None, max_length=255)
    description: str = Field(..., min_length=1)
    severity: Severity
    impact: Optional[str] = None
    technical_details: Optional[str] = None
    steps_to_reproduce: Optional[str] = None
    mitigations: Optional[str] = None
    references: Optional[str] = None
    cvss_score: Optional[float] = Field(None, ge=0.0, le=10.0)
    cvss_vector: Optional[str] = Field(None, max_length=100)

class FindingCreate(FindingBase):
    engagement_id: str
    asset_ids: list[str] = []
    asset_port_ids: Optional[dict[str, list[str]]] = None  # {asset_id: [port_id, ...]}
    tag_ids: list[str] = []
    testcase_id: Optional[str] = None
    attack_technique_ids: list[str] = []

class FindingUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    category: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = Field(None, min_length=1)
    severity: Optional[Severity] = None
    status: Optional[FindingStatus] = None
    impact: Optional[str] = None
    technical_details: Optional[str] = None
    steps_to_reproduce: Optional[str] = None
    mitigations: Optional[str] = None
    references: Optional[str] = None
    cvss_score: Optional[float] = Field(None, ge=0.0, le=10.0)
    cvss_vector: Optional[str] = Field(None, max_length=100)
    asset_ids: Optional[list[str]] = None
    asset_port_ids: Optional[dict[str, list[str]]] = None  # {asset_id: [port_id, ...]}
    tag_ids: Optional[list[str]] = None
    attack_technique_ids: Optional[list[str]] = None

class FindingResponse(FindingBase):
    id: str
    engagement_id: str
    status: FindingStatus
    created_by: str
    created_at: datetime
    updated_at: datetime
    updated_by: Optional[str] = None
    created_by_username: Optional[str] = None
    created_by_profile_photo: Optional[str] = None
    evidence: list[EvidenceResponse] = []
    assets: list[LinkedAssetResponse] = []
    tags: list[TagResponse] = []
    testcases: list[LinkedTestCaseResponse] = []
    vault_items: list[LinkedVaultItemResponse] = []
    cleanup_artifacts: list[LinkedCleanupArtifactResponse] = []
    attack_technique_ids: list[str] = []
    unresolved_thread_count: int = 0

    class Config:
        from_attributes = True


# Findings Template Schemas
class FindingTemplateBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    category: Optional[str] = Field(None, max_length=255)
    description: str = Field(..., min_length=1)
    impact: Optional[str] = None
    mitigations: Optional[str] = None
    references: Optional[str] = None
    attack_technique_ids: list[str] = []

class FindingTemplateCreate(FindingTemplateBase):
    pass

class FindingTemplateUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    category: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = Field(None, min_length=1)
    impact: Optional[str] = None
    mitigations: Optional[str] = None
    references: Optional[str] = None
    attack_technique_ids: Optional[list[str]] = None

class FindingTemplateResponse(FindingTemplateBase):
    id: str
    created_at: datetime
    updated_at: datetime
    created_by: str
    updated_by: Optional[str] = None
    status: TemplateStatus
    submitted_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
    published_by: Optional[str] = None
    review_note: Optional[str] = None

    class Config:
        from_attributes = True

