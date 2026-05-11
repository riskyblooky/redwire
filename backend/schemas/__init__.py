from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class AssetBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    asset_type: str
    identifier: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = None
    notes: Optional[str] = None

class AssetCreate(AssetBase):
    engagement_id: str

class AssetUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    asset_type: Optional[str] = None
    identifier: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = None
    notes: Optional[str] = None

class AssetResponse(AssetBase):
    id: str
    engagement_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Evidence schemas
class EvidenceBase(BaseModel):
    description: Optional[str] = Field(None, max_length=500)

class EvidenceResponse(EvidenceBase):
    id: str
    finding_id: str
    filename: str
    original_filename: str
    file_size: int
    mime_type: Optional[str] = None
    uploaded_at: datetime

    class Config:
        from_attributes = True


# TestCase schemas

class TestCaseBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    category: str
    description: str = Field(..., min_length=1)
    steps: Optional[str] = None
    expected_result: Optional[str] = None

class TestCaseCreate(TestCaseBase):
    engagement_id: Optional[str] = None

class TestCaseUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    category: Optional[str] = None
    description: Optional[str] = Field(None, min_length=1)
    steps: Optional[str] = None
    expected_result: Optional[str] = None
    actual_result: Optional[str] = None
    is_executed: Optional[bool] = None
    is_successful: Optional[bool] = None
    notes: Optional[str] = None

class TestCaseResponse(TestCaseBase):
    id: str
    engagement_id: Optional[str] = None
    actual_result: Optional[str] = None
    is_executed: bool
    is_successful: Optional[bool] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Calendar schemas
class CalendarEventBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    start_time: datetime
    end_time: datetime
    location: Optional[str] = Field(None, max_length=255)
    is_all_day: bool = False

class CalendarEventCreate(CalendarEventBase):
    pass

class CalendarEventUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    location: Optional[str] = Field(None, max_length=255)
    is_all_day: Optional[bool] = None

class CalendarEventResponse(CalendarEventBase):
    id: str
    created_by: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
