from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List
from models.discussion import ResourceType

# Thread Schemas
class ThreadCreate(BaseModel):
    engagement_id: str
    resource_type: ResourceType
    resource_id: Optional[str] = None
    title: str

class ThreadUpdate(BaseModel):
    title: Optional[str] = None
    is_resolved: Optional[bool] = None

class ThreadResponse(BaseModel):
    id: str
    engagement_id: str
    resource_type: ResourceType
    resource_id: Optional[str]
    title: str
    created_by: str
    created_at: datetime
    is_resolved: bool
    comment_count: Optional[int] = 0

    class Config:
        from_attributes = True

# Comment Schemas
class CommentCreate(BaseModel):
    thread_id: str
    # GHSA-82jh-8f6p-vgx9: cap body length at the schema layer. The body
    # flows into notify_mentions which runs a regex with O(n) materialized
    # output; without a cap an attacker could drive multi-GB allocations
    # on a single worker. 32 KiB comfortably accommodates a long postmortem.
    content: str = Field(..., max_length=32768)
    is_resolvable: bool = False

class CommentUpdate(BaseModel):
    content: Optional[str] = Field(None, max_length=32768)
    is_resolved: Optional[bool] = None

class CommentResponse(BaseModel):
    id: str
    thread_id: str
    content: str
    created_by: str
    created_at: datetime
    is_resolvable: bool
    is_resolved: bool
    resolved_by: Optional[str]
    resolved_at: Optional[datetime]
    author_name: Optional[str] = None
    author_profile_photo: Optional[str] = None
    resolver_name: Optional[str] = None

    class Config:
        from_attributes = True

# Activity Log Schemas
class ActivityLogResponse(BaseModel):
    id: str
    engagement_id: str
    user_id: str
    action: str
    resource_type: ResourceType
    resource_id: str
    resource_name: Optional[str]
    details: Optional[str]
    created_at: datetime
    user_name: Optional[str] = None

    class Config:
        from_attributes = True
