from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class InfraVaultItemCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    item_type: str  # CREDENTIAL, KEY, FILE, NOTE
    username: Optional[str] = None
    password: Optional[str] = None
    note: Optional[str] = None
    description: Optional[str] = None


class InfraVaultItemUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    item_type: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    note: Optional[str] = None
    description: Optional[str] = None


class InfraVaultItemResponse(BaseModel):
    id: str
    infra_item_id: str
    name: str
    item_type: str
    username: Optional[str] = None
    password: Optional[str] = None
    note: Optional[str] = None
    filename: Optional[str] = None
    description: Optional[str] = None
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    created_by_username: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class InfraVaultAccessResponse(BaseModel):
    user_id: str
    username: str
    display_name: Optional[str] = None
    profile_photo: Optional[str] = None
    granted_by: Optional[str] = None
    granted_at: datetime
    can_manage: bool = False

    class Config:
        from_attributes = True


class InfraVaultAccessGrant(BaseModel):
    """Body for POST /infra/items/{id}/vault/access. user_id can also be
    passed as a query param for back-compat with the existing clients."""
    user_id: Optional[str] = None
    can_manage: bool = False
