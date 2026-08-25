from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime

TagEntityType = Literal["finding", "testcase", "engagement"]


class TagCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    color: Optional[str] = Field(None, max_length=20)
    entity_type: TagEntityType = "finding"


class TagUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=50)
    color: Optional[str] = Field(None, max_length=20)


class TagResponse(BaseModel):
    id: str
    name: str
    color: Optional[str] = None
    entity_type: str = "finding"
    created_at: datetime

    class Config:
        from_attributes = True
