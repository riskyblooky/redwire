from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from models.asset_port import PortProtocol, PortState
from schemas._field_limits import (
    LONG_TEXT,
    NAME,
    SHORT_LABEL,
    TITLE,
    UUID_FIELD,
)


class LinkedCleanupArtifactResponse(BaseModel):
    id: str
    title: str
    artifact_type: str
    status: str

    class Config:
        from_attributes = True

class LinkedTestCaseResponse(BaseModel):
    id: str
    title: str
    category: str

    class Config:
        from_attributes = True

class LinkedVaultItemResponse(BaseModel):
    id: str
    name: str
    item_type: str

    class Config:
        from_attributes = True

class LinkedFindingResponse(BaseModel):
    id: str
    title: str
    severity: str

    class Config:
        from_attributes = True


class AssetPortCreate(BaseModel):
    port_number: int = Field(..., ge=1, le=65535)
    protocol: PortProtocol = PortProtocol.TCP
    service_name: Optional[str] = Field(None, max_length=SHORT_LABEL)
    state: PortState = PortState.OPEN
    version: Optional[str] = Field(None, max_length=SHORT_LABEL)


class AssetPortUpdate(BaseModel):
    port_number: Optional[int] = Field(None, ge=1, le=65535)
    protocol: Optional[PortProtocol] = None
    service_name: Optional[str] = Field(None, max_length=SHORT_LABEL)
    state: Optional[PortState] = None
    version: Optional[str] = Field(None, max_length=SHORT_LABEL)


class AssetPortResponse(BaseModel):
    id: str
    asset_id: str
    port_number: int
    protocol: PortProtocol
    service_name: Optional[str] = None
    state: PortState
    version: Optional[str] = None

    class Config:
        from_attributes = True


class AssetBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=NAME)
    asset_type: str = Field(..., max_length=SHORT_LABEL)
    identifier: str = Field(..., min_length=1, max_length=TITLE)
    description: Optional[str] = Field(None, max_length=LONG_TEXT)
    notes: Optional[str] = Field(None, max_length=LONG_TEXT)
    is_pwned: bool = False
    is_scanned: bool = False
    in_scope: bool = True
    custom_fields: Optional[dict] = None

class AssetCreate(AssetBase):
    engagement_id: str = Field(..., max_length=UUID_FIELD)

class AssetUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=NAME)
    asset_type: Optional[str] = Field(None, max_length=SHORT_LABEL)
    identifier: Optional[str] = Field(None, min_length=1, max_length=TITLE)
    description: Optional[str] = Field(None, max_length=LONG_TEXT)
    notes: Optional[str] = Field(None, max_length=LONG_TEXT)
    is_pwned: Optional[bool] = None
    is_scanned: Optional[bool] = None
    in_scope: Optional[bool] = None
    custom_fields: Optional[dict] = None

class AssetResponse(AssetBase):
    id: str
    engagement_id: str
    is_pwned: bool
    is_scanned: bool
    in_scope: bool
    created_at: datetime
    updated_at: datetime
    created_by: str
    updated_by: Optional[str] = None
    created_by_username: Optional[str] = None
    created_by_profile_photo: Optional[str] = None
    unresolved_thread_count: int = 0
    cleanup_artifacts: List[LinkedCleanupArtifactResponse] = []
    testcases: List[LinkedTestCaseResponse] = []
    vault_items: List[LinkedVaultItemResponse] = []
    findings: List[LinkedFindingResponse] = []
    ports: List[AssetPortResponse] = []
    port_ids: Optional[List[str]] = None  # Populated when asset is linked via join table
    remediated: bool = False
    remediated_at: Optional[str] = None
    remediated_by: Optional[str] = None

    class Config:
        from_attributes = True


class AssetImportResult(BaseModel):
    created: int = 0
    skipped: int = 0
    ports_added: int = 0
    errors: List[str] = []
