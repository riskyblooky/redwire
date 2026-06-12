from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from models.template_status import TemplateStatus
from schemas._field_limits import (
    LONG_TEXT,
    SHORT_LABEL,
    SLUG,
    TITLE,
    UUID_FIELD,
)


class RunbookItemCreate(BaseModel):
    template_id: str = Field(..., max_length=UUID_FIELD)
    temp_key: str = Field(..., max_length=SLUG, description="Temporary client-side key for referencing parent items during creation")
    parent_temp_key: Optional[str] = Field(None, max_length=SLUG, description="temp_key of parent item, null for root items")
    sort_order: int = 0


class RunbookCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=TITLE)
    description: Optional[str] = Field(None, max_length=LONG_TEXT)
    runbook_type: Optional[str] = Field(None, max_length=SHORT_LABEL)
    items: List[RunbookItemCreate] = []


class RunbookUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=TITLE)
    description: Optional[str] = Field(None, max_length=LONG_TEXT)
    runbook_type: Optional[str] = Field(None, max_length=SHORT_LABEL)
    items: Optional[List[RunbookItemCreate]] = None


class RunbookItemTemplateResponse(BaseModel):
    id: str
    title: str
    category: str
    description: str
    steps: Optional[str] = None
    expected_result: Optional[str] = None

    class Config:
        from_attributes = True


class RunbookItemResponse(BaseModel):
    id: str
    runbook_id: str
    template_id: str
    parent_id: Optional[str] = None
    sort_order: int
    template: Optional[RunbookItemTemplateResponse] = None

    class Config:
        from_attributes = True


class RunbookResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    runbook_type: Optional[str] = None
    items: List[RunbookItemResponse] = []
    created_at: datetime
    updated_at: datetime
    created_by: str
    updated_by: Optional[str] = None
    status: TemplateStatus
    submitted_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
    published_by: Optional[str] = None
    review_note: Optional[str] = None

    class Config:
        from_attributes = True
