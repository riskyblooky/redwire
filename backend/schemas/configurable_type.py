from pydantic import BaseModel, Field
from typing import Optional
from schemas._field_limits import (
    DESCRIPTION,
    HEX_COLOR,
)


class ConfigurableTypeBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=DESCRIPTION)
    color: Optional[str] = Field("#6366f1", max_length=HEX_COLOR)


class ConfigurableTypeCreate(ConfigurableTypeBase):
    pass


class ConfigurableTypeUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=DESCRIPTION)
    color: Optional[str] = Field(None, max_length=HEX_COLOR)


class ConfigurableTypeResponse(ConfigurableTypeBase):
    id: str
    category: str
    is_system: bool
    sort_order: int

    class Config:
        from_attributes = True
