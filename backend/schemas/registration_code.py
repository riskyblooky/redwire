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
    # The server generates the code with a CSPRNG and ignores any client-
    # supplied value -- Math.random()-derived codes are predictable from a
    # single observation. Field stays Optional so older clients that still
    # post {"code": ...} don't 422. GHSA-gc2q-wm5m-59xm.
    code: Optional[str] = None

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
