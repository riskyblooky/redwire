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

class VaultItemResponse(BaseModel):
    """Metadata-only view of a vault item — never carries decrypted
    plaintext on the wire. GHSA-fp69-w2mg-4pqp follow-up: list / create /
    update endpoints return this shape, the per-item reveal endpoint
    returns ``VaultItemRevealResponse`` and writes an audit log row.

    Inherits from BaseModel (not VaultItemBase) so that adding a new
    encrypted field to the create/update shape doesn't accidentally
    leak it through the response.
    """
    id: str
    engagement_id: str
    name: str
    item_type: str
    description: Optional[str] = None
    # has_* booleans let the UI render password-set indicators without
    # ever revealing the value.
    has_username: bool = False
    has_password: bool = False
    has_note: bool = False
    # Server-side classification: is the stored password value shaped
    # like a known hash format (NTLM/MD5/SHA1/bcrypt/…)? Lets the UI
    # surface a "Crack this hash" affordance without revealing the
    # plaintext. Computed once at decrypt time then the plaintext is
    # dropped before serialisation.
    password_looks_like_hash: bool = False
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


class VaultItemRevealResponse(VaultItemResponse):
    """Response shape for ``GET /vault/{item_id}/reveal``. Re-adds the
    three decrypted fields the metadata-only response strips. The reveal
    handler is the only endpoint that returns this shape, and it writes
    a ``accessed_vault_secret`` activity-log row (deduped per
    user/item/5-minute window in Redis) before returning the plaintext.
    """
    username: Optional[str] = None
    password: Optional[str] = None
    note: Optional[str] = None
