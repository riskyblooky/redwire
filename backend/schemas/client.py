from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import datetime
from schemas.configurable_type import ConfigurableTypeResponse
from schemas._field_limits import DESCRIPTION, EMAIL, LONG_TEXT, NAME, UUID_FIELD


# ============ Client Schemas ============

class ClientBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=NAME)
    description: Optional[str] = Field(None, max_length=DESCRIPTION)
    client_type_id: Optional[str] = Field(None, max_length=UUID_FIELD)
    parent_id: Optional[str] = Field(None, max_length=UUID_FIELD)
    contact_name: Optional[str] = Field(None, max_length=NAME)
    contact_email: Optional[str] = Field(None, max_length=EMAIL)
    notes: Optional[str] = Field(None, max_length=LONG_TEXT)

class ClientCreate(ClientBase):
    pass

class ClientUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=NAME)
    description: Optional[str] = Field(None, max_length=DESCRIPTION)
    client_type_id: Optional[str] = Field(None, max_length=UUID_FIELD)
    parent_id: Optional[str] = Field(None, max_length=UUID_FIELD)
    contact_name: Optional[str] = Field(None, max_length=NAME)
    contact_email: Optional[str] = Field(None, max_length=EMAIL)
    notes: Optional[str] = Field(None, max_length=LONG_TEXT)

class ClientResponse(ClientBase):
    id: str
    sort_order: int
    client_type: Optional[ConfigurableTypeResponse] = None
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str] = None
    engagement_count: int = 0

    class Config:
        from_attributes = True

class ClientTreeNode(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    client_type_id: Optional[str] = None
    client_type: Optional[ConfigurableTypeResponse] = None
    parent_id: Optional[str] = None
    sort_order: int = 0
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    engagement_count: int = 0
    children: List["ClientTreeNode"] = []

    class Config:
        from_attributes = True


# ============ Reorder Schema ============

class ReorderItem(BaseModel):
    id: str
    sort_order: int
    parent_id: Optional[str] = None

class ClientReorderRequest(BaseModel):
    items: List[ReorderItem]


# ============ Stats / Comparison Schemas ============

class EngagementSummary(BaseModel):
    """Per-engagement metrics, used for the Engagements list, Trends chart, and comparisons."""
    id: str
    name: str
    status: str
    engagement_type: Optional[str] = None
    client_id: Optional[str] = None
    client_name: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    finding_count: int = 0
    findings_by_severity: Dict[str, int] = Field(default_factory=dict)
    findings_by_status: Dict[str, int] = Field(default_factory=dict)
    open_findings: int = 0
    closed_findings: int = 0
    mttr_days: Optional[float] = None  # null if no closed findings


class ClientStatsResponse(BaseModel):
    client_id: str
    include_descendants: bool = False
    engagement_count: int = 0
    engagements_by_status: Dict[str, int] = Field(default_factory=dict)
    finding_count: int = 0
    findings_by_severity: Dict[str, int] = Field(default_factory=dict)
    findings_by_status: Dict[str, int] = Field(default_factory=dict)
    open_findings: int = 0
    closed_findings: int = 0
    mttr_days: Optional[float] = None
    first_engagement_at: Optional[datetime] = None
    last_engagement_at: Optional[datetime] = None


class EngagementCompareResponse(BaseModel):
    a: EngagementSummary
    b: EngagementSummary
    delta: Dict[str, object]  # finding_count, by_severity (dict), open_findings, closed_findings, mttr_days
