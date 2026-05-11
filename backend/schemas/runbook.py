from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from models.template_status import TemplateStatus


class RunbookItemCreate(BaseModel):
    template_id: str
    temp_key: str = Field(..., description="Temporary client-side key for referencing parent items during creation")
    parent_temp_key: Optional[str] = Field(None, description="temp_key of parent item, null for root items")
    sort_order: int = 0


class RunbookCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = None
    runbook_type: Optional[str] = None
    items: List[RunbookItemCreate] = []


class RunbookUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = None
    runbook_type: Optional[str] = None
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
