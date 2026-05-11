from pydantic import BaseModel, Field
from typing import Optional


class ConfigurableTypeBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    color: Optional[str] = "#6366f1"


class ConfigurableTypeCreate(ConfigurableTypeBase):
    pass


class ConfigurableTypeUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    color: Optional[str] = None


class ConfigurableTypeResponse(ConfigurableTypeBase):
    id: str
    category: str
    is_system: bool
    sort_order: int

    class Config:
        from_attributes = True
