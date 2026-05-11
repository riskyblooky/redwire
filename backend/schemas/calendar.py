from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class CalendarEventBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    start_time: datetime
    end_time: datetime
    location: Optional[str] = Field(None, max_length=255)
    is_all_day: bool = False
    event_type: str = Field("EVENT", max_length=20)  # EVENT or OOO

class CalendarEventCreate(CalendarEventBase):
    pass

class CalendarEventUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    location: Optional[str] = None
    is_all_day: Optional[bool] = None
    event_type: Optional[str] = Field(None, max_length=20)

class CalendarEventResponse(CalendarEventBase):
    id: str
    created_by: str
    created_at: datetime
    updated_at: datetime
    updated_by: Optional[str] = None

    class Config:
        from_attributes = True
