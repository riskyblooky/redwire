from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class TagCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    color: Optional[str] = Field(None, max_length=20)


class TagUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=50)
    color: Optional[str] = Field(None, max_length=20)


class TagResponse(BaseModel):
    id: str
    name: str
    color: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
