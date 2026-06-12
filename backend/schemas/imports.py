"""
schemas/imports.py — Pydantic models for the import preview/commit flow.
"""

from pydantic import BaseModel, Field
from typing import Optional
from schemas._field_limits import (
    CVSS_VECTOR,
    ENUM_STR,
    LONG_TEXT,
    NAME,
    SHORT_LABEL,
    TITLE,
    UUID_FIELD,
)


class PreviewPort(BaseModel):
    port_number: int
    protocol: str = Field("TCP", max_length=ENUM_STR)
    service_name: Optional[str] = Field(None, max_length=SHORT_LABEL)
    state: str = Field("OPEN", max_length=ENUM_STR)
    version: Optional[str] = Field(None, max_length=SHORT_LABEL)


class PreviewAsset(BaseModel):
    index: int
    name: str = Field(..., max_length=NAME)
    asset_type: str = Field(..., max_length=SHORT_LABEL)
    identifier: str = Field(..., max_length=TITLE)
    description: str = Field("", max_length=LONG_TEXT)
    ports: list[PreviewPort] = []
    is_duplicate: bool = False          # True if identifier already exists in engagement


class PreviewFinding(BaseModel):
    index: int
    title: str = Field(..., max_length=TITLE)
    severity: str = Field(..., max_length=ENUM_STR)
    description: str = Field("", max_length=LONG_TEXT)
    impact: Optional[str] = Field(None, max_length=LONG_TEXT)
    mitigations: Optional[str] = Field(None, max_length=LONG_TEXT)
    references: Optional[str] = Field(None, max_length=LONG_TEXT)
    cvss_score: Optional[float] = None
    cvss_vector: Optional[str] = Field(None, max_length=CVSS_VECTOR)
    category: Optional[str] = Field(None, max_length=SHORT_LABEL)
    affected_asset_count: int = 0
    is_duplicate: bool = False          # True if title already exists in engagement


class PreviewResponse(BaseModel):
    source_tool: str = Field(..., max_length=SHORT_LABEL)
    assets: list[PreviewAsset] = []
    findings: list[PreviewFinding] = []
    warnings: list[str] = []
    metadata: dict = {}


class CommitRequest(BaseModel):
    engagement_id: str = Field(..., max_length=UUID_FIELD)
    import_assets: bool = True
    import_findings: bool = True
    asset_indices: Optional[list[int]] = None   # None = all
    finding_indices: Optional[list[int]] = None  # None = all


class CommitResponse(BaseModel):
    assets_created: int = 0
    assets_skipped: int = 0
    findings_created: int = 0
    findings_skipped: int = 0
    ports_added: int = 0
    finding_asset_links: int = 0
    errors: list[str] = []
