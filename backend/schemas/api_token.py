"""Pydantic schemas for API token endpoints."""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ApiTokenCreate(BaseModel):
    """Request body for creating an API token."""
    name: str = Field(..., min_length=1, max_length=100)
    permission: str = Field("ro", pattern="^(ro|rw)$")
    expires_at: Optional[datetime] = None


class ApiTokenAdminCreate(ApiTokenCreate):
    """Admin variant — can specify target user."""
    user_id: str


class ApiTokenResponse(BaseModel):
    """Token metadata (never includes the raw token)."""
    id: str
    name: str
    token_prefix: str
    permission: str
    user_id: str
    created_at: datetime
    last_used_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    is_active: bool
    created_by: Optional[str] = None

    class Config:
        from_attributes = True


class ApiTokenCreated(ApiTokenResponse):
    """Response after token creation — includes the raw token (shown once)."""
    raw_token: str


class ApiTokenAdminResponse(ApiTokenResponse):
    """Admin listing — includes user info."""
    username: Optional[str] = None
    user_full_name: Optional[str] = None
