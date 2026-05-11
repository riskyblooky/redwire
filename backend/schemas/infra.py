from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


# ── Infra Item Schemas ───────────────────────────────────────────

class InfraItemCreate(BaseModel):
    name: str
    infra_type: Optional[str] = "OTHER"
    status: Optional[str] = "ACTIVE"
    ip_address: Optional[str] = None
    internal_ip: Optional[str] = None
    hostname: Optional[str] = None
    provider: Optional[str] = None
    region: Optional[str] = None
    os: Optional[str] = None
    point_of_presence: Optional[str] = None
    notes: Optional[str] = None


class InfraItemUpdate(BaseModel):
    name: Optional[str] = None
    infra_type: Optional[str] = None
    status: Optional[str] = None
    ip_address: Optional[str] = None
    internal_ip: Optional[str] = None
    hostname: Optional[str] = None
    provider: Optional[str] = None
    region: Optional[str] = None
    os: Optional[str] = None
    point_of_presence: Optional[str] = None
    notes: Optional[str] = None


class InfraItemResponse(BaseModel):
    id: str
    name: str
    infra_type: str
    status: str
    ip_address: Optional[str] = None
    internal_ip: Optional[str] = None
    hostname: Optional[str] = None
    provider: Optional[str] = None
    region: Optional[str] = None
    os: Optional[str] = None
    point_of_presence: Optional[str] = None
    notes: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class LinkedEntitySummary(BaseModel):
    id: str
    title: str
    type: str  # 'finding', 'testcase', 'note'


class InfraItemDetail(InfraItemResponse):
    linked_findings: List[LinkedEntitySummary] = []
    linked_testcases: List[LinkedEntitySummary] = []
    linked_notes: List[LinkedEntitySummary] = []
    linked_count: int = 0


# ── Link/Unlink Schemas ─────────────────────────────────────────

class InfraLinkRequest(BaseModel):
    entity_type: str  # 'finding', 'testcase', 'note'
    entity_id: str
