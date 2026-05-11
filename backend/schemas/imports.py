"""
schemas/imports.py — Pydantic models for the import preview/commit flow.
"""

from pydantic import BaseModel
from typing import Optional


class PreviewPort(BaseModel):
    port_number: int
    protocol: str = "TCP"
    service_name: Optional[str] = None
    state: str = "OPEN"
    version: Optional[str] = None


class PreviewAsset(BaseModel):
    index: int
    name: str
    asset_type: str
    identifier: str
    description: str = ""
    ports: list[PreviewPort] = []
    is_duplicate: bool = False          # True if identifier already exists in engagement


class PreviewFinding(BaseModel):
    index: int
    title: str
    severity: str
    description: str = ""
    impact: Optional[str] = None
    mitigations: Optional[str] = None
    references: Optional[str] = None
    cvss_score: Optional[float] = None
    cvss_vector: Optional[str] = None
    category: Optional[str] = None
    affected_asset_count: int = 0
    is_duplicate: bool = False          # True if title already exists in engagement


class PreviewResponse(BaseModel):
    source_tool: str
    assets: list[PreviewAsset] = []
    findings: list[PreviewFinding] = []
    warnings: list[str] = []
    metadata: dict = {}


class CommitRequest(BaseModel):
    engagement_id: str
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
