from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from schemas._field_limits import (
    ENUM_STR,
    HOSTNAME,
    LONG_TEXT,
    NAME,
    SHORT_LABEL,
    UUID_FIELD,
)


# ── Spray Result schemas ─────────────────────────────────────────

class SprayResultPreview(BaseModel):
    """A single parsed result from nxc log — used in preview before commit."""
    username: str = Field(..., max_length=NAME)
    domain: Optional[str] = Field(None, max_length=HOSTNAME)
    result: str = Field(..., max_length=ENUM_STR)           # success / success_admin / failed / locked / disabled
    status_code: Optional[str] = Field(None, max_length=ENUM_STR)
    is_admin: bool = False
    target_host: Optional[str] = Field(None, max_length=HOSTNAME)
    target_port: Optional[int] = None
    password: Optional[str] = Field(None, max_length=NAME)  # Plaintext during preview/commit; encrypted at rest


class SprayResultResponse(BaseModel):
    """Result row returned to the frontend. `password` is intentionally omitted
    from the default detail view — use a dedicated reveal endpoint if needed."""
    id: str
    campaign_id: str
    username: str
    domain: Optional[str] = None
    result: str
    status_code: Optional[str] = None
    is_admin: bool = False
    target_host: Optional[str] = None
    target_port: Optional[int] = None
    vault_item_id: Optional[str] = None
    asset_id: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ── Spray Campaign schemas ───────────────────────────────────────

class SprayImportPreview(BaseModel):
    """Returned by POST /spray/import — preview before commit."""
    protocol: Optional[str] = Field(None, max_length=ENUM_STR)
    target_host: Optional[str] = Field(None, max_length=HOSTNAME)      # CLI target if recoverable, else single host, else null
    target_port: Optional[int] = None
    target_hostname: Optional[str] = Field(None, max_length=HOSTNAME)
    domain: Optional[str] = Field(None, max_length=HOSTNAME)
    password_used: Optional[str] = Field(None, max_length=NAME)    # Set only when ALL results share one password
    total_attempts: int = 0
    successful: int = 0
    locked_out: int = 0
    failed: int = 0
    host_count: int = 0                    # Number of distinct hosts touched by the run
    command_line: Optional[str] = Field(None, max_length=SHORT_LABEL * 4)     # Raw nxc command from the log preamble, if present
    matched_asset_count: int = 0           # Hosts already present in the engagement's asset inventory
    unmatched_hosts: List[str] = []        # Hosts not yet inventoried — candidates for auto-create
    results: List[SprayResultPreview] = []
    imported_from: Optional[str] = Field(None, max_length=NAME)


class SprayCommitRequest(BaseModel):
    """Request body for POST /spray/commit — save previewed results."""
    engagement_id: str = Field(..., max_length=UUID_FIELD)
    name: str = Field(..., min_length=1, max_length=NAME)
    protocol: Optional[str] = Field(None, max_length=ENUM_STR)
    target_host: Optional[str] = Field(None, max_length=HOSTNAME)
    target_port: Optional[int] = None
    target_hostname: Optional[str] = Field(None, max_length=HOSTNAME)
    domain: Optional[str] = Field(None, max_length=HOSTNAME)
    password_used: Optional[str] = Field(None, max_length=NAME)
    notes: Optional[str] = Field(None, max_length=LONG_TEXT)
    imported_from: Optional[str] = Field(None, max_length=NAME)
    # When true, the commit endpoint creates Asset rows for any per-result
    # target_host that isn't already in the engagement's inventory, then
    # links the spray results to those new assets.
    create_missing_assets: bool = False
    results: List[SprayResultPreview] = []


class SprayCampaignResponse(BaseModel):
    id: str
    engagement_id: str
    name: str
    protocol: Optional[str] = None
    target_host: Optional[str] = None
    target_port: Optional[int] = None
    target_hostname: Optional[str] = None
    domain: Optional[str] = None
    password_used: Optional[str] = None
    total_attempts: int = 0
    successful: int = 0
    locked_out: int = 0
    failed: int = 0
    status: Optional[str] = None
    notes: Optional[str] = None
    imported_from: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str] = None

    class Config:
        from_attributes = True


class SprayCampaignDetailResponse(SprayCampaignResponse):
    results: List[SprayResultResponse] = []
