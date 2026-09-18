from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List
from models.discussion import ResourceType
from schemas._field_limits import TITLE, UUID_FIELD

# Anchor for peer-review "highlight" comments — points a thread at a span of text
# inside one field of the resource. See docs/anchored-comments-peer-review.md.
class ThreadAnchor(BaseModel):
    field: str = Field(..., max_length=64)          # e.g. "description", "steps"
    quote: str = Field(..., max_length=2048)        # highlighted text
    prefix: Optional[str] = Field(None, max_length=128)  # context before the quote
    suffix: Optional[str] = Field(None, max_length=128)  # context after the quote
    occurrence: int = Field(0, ge=0)                # index among identical quotes

class ThreadAnchorOut(ThreadAnchor):
    status: Optional[str] = None                    # "active" | "orphaned"

# Thread Schemas
class ThreadCreate(BaseModel):
    engagement_id: str = Field(..., max_length=UUID_FIELD)
    resource_type: ResourceType
    resource_id: Optional[str] = Field(None, max_length=UUID_FIELD)
    title: str = Field(..., max_length=TITLE)
    anchor: Optional[ThreadAnchor] = None

class ThreadUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=TITLE)
    is_resolved: Optional[bool] = None
    anchor: Optional[ThreadAnchor] = None           # auto-refresh on save (§7.4)

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
    anchor: Optional[ThreadAnchorOut] = None

    class Config:
        from_attributes = True

# Comment Schemas
class CommentCreate(BaseModel):
    thread_id: str = Field(..., max_length=UUID_FIELD)
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
    # Stored as a free String on the model (many loggers use types outside the
    # ResourceType enum: spray, user, stats_page, import, …). Typing this as the
    # enum made a single out-of-enum row 500 the entire log fetch.
    resource_type: str
    resource_id: str
    resource_name: Optional[str]
    details: Optional[str]
    created_at: datetime
    user_name: Optional[str] = None

    class Config:
        from_attributes = True
