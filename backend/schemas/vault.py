from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

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
    name: str = Field(..., min_length=1, max_length=255)
    item_type: str
    username: Optional[str] = Field(None, max_length=255)
    password: Optional[str] = Field(None, max_length=1000)
    note: Optional[str] = None
    description: Optional[str] = None

class VaultItemCreate(VaultItemBase):
    engagement_id: str

class VaultItemUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    item_type: Optional[str] = None
    username: Optional[str] = Field(None, max_length=255)
    password: Optional[str] = Field(None, max_length=1000)
    note: Optional[str] = None
    description: Optional[str] = None

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
