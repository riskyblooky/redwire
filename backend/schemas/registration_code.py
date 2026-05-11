from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class RegistrationCodeBase(BaseModel):
    code: str
    label: Optional[str] = None
    max_uses: int = 1
    expires_at: Optional[datetime] = None
    is_active: bool = True

class RegistrationCodeCreate(RegistrationCodeBase):
    pass

class RegistrationCodeUpdate(BaseModel):
    label: Optional[str] = None
    max_uses: Optional[int] = None
    expires_at: Optional[datetime] = None
    is_active: Optional[bool] = None

class RegistrationCodeResponse(RegistrationCodeBase):
    id: str
    used_count: int
    created_at: datetime
    created_by: str

    class Config:
        from_attributes = True

class RegistrationCodeUserResponse(BaseModel):
    id: str
    username: str
    email: str
    full_name: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
