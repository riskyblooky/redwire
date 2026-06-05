from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from models.engagement import EngagementStatus
from schemas.user import UserSummary
from schemas.rbac import EngagementAssignmentCreate, EngagementAssignmentResponse
from schemas.client import ClientResponse as ClientSchemaResponse


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
    id: str
    planned_start: Optional[datetime] = None
    planned_end: Optional[datetime] = None


# ── Engagement Schemas ───────────────────────────────────────────

class EngagementBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    client_name: str = Field(..., min_length=1, max_length=255)
    client_id: Optional[str] = None
    engagement_type: str
    status: Optional[EngagementStatus] = EngagementStatus.PLANNING
    description: Optional[str] = None
    scope: Optional[str] = None
    objectives: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    # Portion marking
    marking_profile_id: Optional[str] = None
    default_classification_level: Optional[str] = Field(None, max_length=20)
    default_classification_suffix: Optional[str] = Field(None, max_length=120)
    ceiling_classification_level: Optional[str] = Field(None, max_length=20)

class EngagementCreate(EngagementBase):
    assigned_user_ids: Optional[List[str]] = []
    assignments: Optional[List[EngagementAssignmentCreate]] = []

class EngagementUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    client_name: Optional[str] = Field(None, min_length=1, max_length=255)
    client_id: Optional[str] = None
    engagement_type: Optional[str] = None
    status: Optional[EngagementStatus] = None
    description: Optional[str] = None
    scope: Optional[str] = None
    objectives: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    marking_profile_id: Optional[str] = None
    default_classification_level: Optional[str] = Field(None, max_length=20)
    default_classification_suffix: Optional[str] = Field(None, max_length=120)
    ceiling_classification_level: Optional[str] = Field(None, max_length=20)
    assigned_user_ids: Optional[List[str]] = None
    assignments: Optional[List[EngagementAssignmentCreate]] = None

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

    class Config:
        from_attributes = True

# Import at bottom to avoid circular import
from schemas.rbac import EngagementAssignmentResponse
