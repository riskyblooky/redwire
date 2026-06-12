from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from schemas._field_limits import (
    ENUM_STR,
    HOSTNAME,
    IP_ADDR,
    LONG_TEXT,
    NAME,
    SHORT_LABEL,
    SLUG,
)


# ── Infra Item Schemas ───────────────────────────────────────────

class InfraItemCreate(BaseModel):
    name: str = Field(..., max_length=NAME)
    infra_type: Optional[str] = Field("OTHER", max_length=SHORT_LABEL)
    status: Optional[str] = Field("ACTIVE", max_length=ENUM_STR)
    ip_address: Optional[str] = Field(None, max_length=IP_ADDR)
    internal_ip: Optional[str] = Field(None, max_length=IP_ADDR)
    hostname: Optional[str] = Field(None, max_length=HOSTNAME)
    provider: Optional[str] = Field(None, max_length=SHORT_LABEL)
    region: Optional[str] = Field(None, max_length=SHORT_LABEL)
    os: Optional[str] = Field(None, max_length=SHORT_LABEL)
    point_of_presence: Optional[str] = Field(None, max_length=SHORT_LABEL)
    notes: Optional[str] = Field(None, max_length=LONG_TEXT)


class InfraItemUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=NAME)
    infra_type: Optional[str] = Field(None, max_length=SHORT_LABEL)
    status: Optional[str] = Field(None, max_length=ENUM_STR)
    ip_address: Optional[str] = Field(None, max_length=IP_ADDR)
    internal_ip: Optional[str] = Field(None, max_length=IP_ADDR)
    hostname: Optional[str] = Field(None, max_length=HOSTNAME)
    provider: Optional[str] = Field(None, max_length=SHORT_LABEL)
    region: Optional[str] = Field(None, max_length=SHORT_LABEL)
    os: Optional[str] = Field(None, max_length=SHORT_LABEL)
    point_of_presence: Optional[str] = Field(None, max_length=SHORT_LABEL)
    notes: Optional[str] = Field(None, max_length=LONG_TEXT)


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
    entity_type: str = Field(..., max_length=ENUM_STR)  # 'finding', 'testcase', 'note'
    entity_id: str = Field(..., max_length=SLUG)
