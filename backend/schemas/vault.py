from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from schemas._field_limits import (
    DESCRIPTION,
    LONG_TEXT,
    NAME,
    SHORT_LABEL,
    UUID_FIELD,
)

class LinkedFindingResponse(BaseModel):
    id: str
    title: str
    severity: str

    class Config:
        from_attributes = True

class LinkedTestCaseResponse(BaseModel):
    id: str
    title: str

    class Config:
        from_attributes = True

class LinkedAssetResponse(BaseModel):
    id: str
    name: str
    asset_type: str
    identifier: Optional[str] = None

    class Config:
        from_attributes = True

class VaultItemBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=NAME)
    item_type: str = Field(..., max_length=SHORT_LABEL)
    username: Optional[str] = Field(None, max_length=NAME)
    password: Optional[str] = Field(None, max_length=4096)
    note: Optional[str] = Field(None, max_length=LONG_TEXT)
    description: Optional[str] = Field(None, max_length=DESCRIPTION)

class VaultItemCreate(VaultItemBase):
    engagement_id: str = Field(..., max_length=UUID_FIELD)

class VaultItemUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=NAME)
    item_type: Optional[str] = Field(None, max_length=SHORT_LABEL)
    username: Optional[str] = Field(None, max_length=NAME)
    password: Optional[str] = Field(None, max_length=4096)
    note: Optional[str] = Field(None, max_length=LONG_TEXT)
    description: Optional[str] = Field(None, max_length=DESCRIPTION)

class VaultItemResponse(VaultItemBase):
    id: str
    engagement_id: str
    filename: Optional[str] = None
    file_path: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    created_by: str
    updated_by: Optional[str] = None
    created_by_username: Optional[str] = None
    created_by_profile_photo: Optional[str] = None
    findings: List[LinkedFindingResponse] = []
    testcases: List[LinkedTestCaseResponse] = []
    assets: List[LinkedAssetResponse] = []

    class Config:
        from_attributes = True
