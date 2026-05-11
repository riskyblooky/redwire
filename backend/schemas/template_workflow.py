"""Shared schemas for the template draft/submit/publish workflow."""
from pydantic import BaseModel, Field


class TemplateRejectRequest(BaseModel):
    review_note: str = Field(..., min_length=1, max_length=2000)
