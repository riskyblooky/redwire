from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from schemas._field_limits import (
    DESCRIPTION,
    ENUM_STR,
    NAME,
)

class CalendarEventBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=NAME)
    description: Optional[str] = Field(None, max_length=DESCRIPTION)
    start_time: datetime
    end_time: datetime
    location: Optional[str] = Field(None, max_length=NAME)
    is_all_day: bool = False
    event_type: str = Field("EVENT", max_length=ENUM_STR)  # EVENT or OOO

class CalendarEventCreate(CalendarEventBase):
    pass

class CalendarEventUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=NAME)
    description: Optional[str] = Field(None, max_length=DESCRIPTION)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    location: Optional[str] = Field(None, max_length=NAME)
    is_all_day: Optional[bool] = None
    event_type: Optional[str] = Field(None, max_length=ENUM_STR)

class CalendarEventResponse(CalendarEventBase):
    id: str
    created_by: str
    created_at: datetime
    updated_at: datetime
    updated_by: Optional[str] = None

    class Config:
        from_attributes = True
