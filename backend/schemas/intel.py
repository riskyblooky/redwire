from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime
from models.intel_item import IntelItemType, IntelSeverity
from utils.ssrf import validate_outbound_url_sync, OutboundURLError
from schemas._field_limits import (
    ENUM_STR,
    LONG_TEXT,
    NAME,
    SHORT_LABEL,
    SLUG,
    TITLE,
    URL,
)


# ── Intel Feed Schemas ───────────────────────────────────────────

class IntelFeedCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=NAME)
    url: str = Field(..., min_length=1, max_length=URL)
    feed_type: str = Field("RSS", max_length=ENUM_STR)
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

# GHSA-7f5w-xj7p-cjj4: constrain source_url to safe web schemes at the
# API boundary. Prior to this the field was `Optional[str]` with no
# scheme check, so an operator could store a `javascript:` URI that
# the finding-detail page then rendered verbatim as `<a href=...>`,
# producing stored XSS on click. Backend rejection is the single load-
# bearing gate; frontend defensive gates layer on top of it.
_SAFE_SOURCE_URL_SCHEMES = ("http://", "https://")


def _validate_source_url(v: Optional[str]) -> Optional[str]:
    if v is None or v == "":
        return v
    if not v.lower().startswith(_SAFE_SOURCE_URL_SCHEMES):
        raise ValueError("source_url must be an http:// or https:// URL")
    return v


class IntelItemCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=TITLE)
    content: Optional[str] = Field(None, max_length=LONG_TEXT)
    source: Optional[str] = Field("manual", max_length=SHORT_LABEL)
    source_url: Optional[str] = Field(None, max_length=URL)
    item_type: IntelItemType = IntelItemType.OTHER
    severity: Optional[IntelSeverity] = None
    cve_id: Optional[str] = Field(None, max_length=SHORT_LABEL)
    published_at: Optional[datetime] = None

    _v_source_url = field_validator("source_url")(_validate_source_url)


class IntelItemUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=TITLE)
    content: Optional[str] = Field(None, max_length=LONG_TEXT)
    source: Optional[str] = Field(None, max_length=SHORT_LABEL)
    source_url: Optional[str] = Field(None, max_length=URL)
    item_type: Optional[IntelItemType] = None
    severity: Optional[IntelSeverity] = None
    cve_id: Optional[str] = Field(None, max_length=SHORT_LABEL)

    _v_source_url = field_validator("source_url")(_validate_source_url)


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
    entity_type: str = Field(..., max_length=ENUM_STR)  # "finding", "testcase", "note"
    entity_id: str = Field(..., max_length=SLUG)
