from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from models.engagement import EngagementStatus
from schemas.user import UserSummary
from schemas.rbac import EngagementAssignmentCreate, EngagementAssignmentResponse
from schemas.client import ClientResponse as ClientSchemaResponse
from schemas.finding import TagResponse
from schemas._field_limits import (
    ENUM_STR,
    LONG_TEXT,
    NAME,
    SHORT_LABEL,
    UUID_FIELD,
)


# ── Phase Schemas ────────────────────────────────────────────────

class EngagementPhaseResponse(BaseModel):
    id: str
    engagement_id: str
    phase_name: str
    sort_order: int
    planned_start: Optional[datetime] = None
    planned_end: Optional[datetime] = None

    class Config:
        from_attributes = True

class EngagementPhaseUpdate(BaseModel):
    id: str = Field(..., max_length=UUID_FIELD)
    planned_start: Optional[datetime] = None
    planned_end: Optional[datetime] = None


# ── Engagement Schemas ───────────────────────────────────────────

class EngagementBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=NAME)
    client_name: str = Field(..., min_length=1, max_length=NAME)
    client_id: Optional[str] = Field(None, max_length=UUID_FIELD)
    engagement_type: str = Field(..., max_length=SHORT_LABEL)
    status: Optional[EngagementStatus] = EngagementStatus.SCOPING
    description: Optional[str] = Field(None, max_length=LONG_TEXT)
    scope: Optional[str] = Field(None, max_length=LONG_TEXT)
    objectives: Optional[str] = Field(None, max_length=LONG_TEXT)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    # Portion marking
    marking_profile_id: Optional[str] = Field(None, max_length=UUID_FIELD)
    default_classification_level: Optional[str] = Field(None, max_length=ENUM_STR)
    default_classification_suffix: Optional[str] = Field(None, max_length=SHORT_LABEL)
    ceiling_classification_level: Optional[str] = Field(None, max_length=ENUM_STR)

class EngagementCreate(EngagementBase):
    # Override the Base's optional start_date to hard-require it at
    # create time. Existing rows may still be null (legacy imports,
    # older creates) — the DB column stays nullable so we don't have
    # to backfill — but every NEW engagement must anchor to a start
    # date so calendar/phase math has a real value to work with.
    start_date: datetime
    assigned_user_ids: Optional[List[str]] = []
    assignments: Optional[List[EngagementAssignmentCreate]] = []
    # Optional tag ids at create time — same shape as findings/testcases.
    # Foreign / unknown ids are silently dropped by the .in_() lookup so a
    # stale client can't poison the row with junk associations.
    tag_ids: Optional[List[str]] = []

class EngagementUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=NAME)
    client_name: Optional[str] = Field(None, min_length=1, max_length=NAME)
    client_id: Optional[str] = Field(None, max_length=UUID_FIELD)
    engagement_type: Optional[str] = Field(None, max_length=SHORT_LABEL)
    status: Optional[EngagementStatus] = None
    description: Optional[str] = Field(None, max_length=LONG_TEXT)
    scope: Optional[str] = Field(None, max_length=LONG_TEXT)
    objectives: Optional[str] = Field(None, max_length=LONG_TEXT)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    marking_profile_id: Optional[str] = Field(None, max_length=UUID_FIELD)
    default_classification_level: Optional[str] = Field(None, max_length=ENUM_STR)
    default_classification_suffix: Optional[str] = Field(None, max_length=SHORT_LABEL)
    ceiling_classification_level: Optional[str] = Field(None, max_length=ENUM_STR)
    assigned_user_ids: Optional[List[str]] = None
    assignments: Optional[List[EngagementAssignmentCreate]] = None
    # None = don't touch, [] = clear all — same semantics as findings.
    tag_ids: Optional[List[str]] = None

class EngagementResponse(EngagementBase):
    id: str
    status: EngagementStatus
    created_by: str
    created_at: datetime
    updated_at: datetime
    updated_by: Optional[str] = None
    assigned_users: List[UserSummary] = []
    assignment_details: List["EngagementAssignmentResponse"] = []
    client: Optional[ClientSchemaResponse] = None
    phases: List[EngagementPhaseResponse] = []
    tags: List[TagResponse] = []

    class Config:
        from_attributes = True

# Import at bottom to avoid circular import
from schemas.rbac import EngagementAssignmentResponse
