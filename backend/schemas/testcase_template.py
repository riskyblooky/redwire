from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from models.template_status import TemplateStatus


class TestCaseTemplateBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    category: str
    description: str
    steps: Optional[str] = None
    expected_result: Optional[str] = None
    attack_technique_ids: list[str] = []


class TestCaseTemplateCreate(TestCaseTemplateBase):
    pass


class TestCaseTemplateUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    category: Optional[str] = None
    description: Optional[str] = None
    steps: Optional[str] = None
    expected_result: Optional[str] = None
    attack_technique_ids: Optional[list[str]] = None


class TestCaseTemplateResponse(TestCaseTemplateBase):
    id: str
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
