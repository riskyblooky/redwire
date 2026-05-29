from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime
from models.intel_item import IntelItemType, IntelSeverity
from utils.ssrf import validate_outbound_url_sync, OutboundURLError


# ── Intel Feed Schemas ───────────────────────────────────────────

class IntelFeedCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    url: str = Field(..., min_length=1)
    feed_type: str = "RSS"
    enabled: bool = True

    @field_validator("url")
    @classmethod
    def _validate_url(cls, v: str) -> str:
        # SSRF guard (GHSA-f33c-g6w5-6xm6): refuse to store a feed URL that
        # points at a non-public address. Re-checked at fetch time too.
        try:
            validate_outbound_url_sync(v)
        except OutboundURLError as e:
            raise ValueError(str(e))
        return v

class IntelFeedResponse(BaseModel):
    id: str
    name: str
    url: str
    feed_type: str
    enabled: bool
    last_fetched_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ── Intel Item Schemas ───────────────────────────────────────────

class IntelItemCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    content: Optional[str] = None
    source: Optional[str] = "manual"
    source_url: Optional[str] = None
    item_type: IntelItemType = IntelItemType.OTHER
    severity: Optional[IntelSeverity] = None
    cve_id: Optional[str] = None
    published_at: Optional[datetime] = None

class IntelItemUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    source: Optional[str] = None
    source_url: Optional[str] = None
    item_type: Optional[IntelItemType] = None
    severity: Optional[IntelSeverity] = None
    cve_id: Optional[str] = None


class LinkedEntitySummary(BaseModel):
    id: str
    title: str
    type: str  # "finding", "testcase", "note"

class IntelItemResponse(BaseModel):
    id: str
    title: str
    content: Optional[str] = None
    source: Optional[str] = None
    source_url: Optional[str] = None
    item_type: IntelItemType
    severity: Optional[IntelSeverity] = None
    cve_id: Optional[str] = None
    published_at: Optional[datetime] = None
    feed_id: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    linked_count: int = 0

    class Config:
        from_attributes = True

class IntelAttachmentResponse(BaseModel):
    id: str
    intel_item_id: str
    original_filename: str
    file_size: int
    mime_type: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class IntelItemDetail(IntelItemResponse):
    linked_findings: List[LinkedEntitySummary] = []
    linked_testcases: List[LinkedEntitySummary] = []
    linked_notes: List[LinkedEntitySummary] = []
    attachments: List[IntelAttachmentResponse] = []


# ── Link/Unlink Schemas ─────────────────────────────────────────

class IntelLinkRequest(BaseModel):
    entity_type: str  # "finding", "testcase", "note"
    entity_id: str
