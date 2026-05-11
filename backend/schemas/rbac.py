from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

# --- Group Schemas ---

class GroupBase(BaseModel):
    name: str
    description: Optional[str] = None

class GroupCreate(GroupBase):
    pass

class GroupUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

class GroupResponse(GroupBase):
    id: str

    class Config:
        from_attributes = True

# --- EngagementRole Schemas ---

class EngagementRoleBase(BaseModel):
    name: str
    description: Optional[str] = None

class EngagementRoleCreate(EngagementRoleBase):
    pass

class EngagementRoleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

class EngagementRoleResponse(EngagementRoleBase):
    id: str

    class Config:
        from_attributes = True

# --- EngagementAssignment Schemas ---

class EngagementAssignmentResponse(BaseModel):
    user_id: str
    engagement_id: str
    role_id: Optional[str] = None
    role: Optional[EngagementRoleResponse] = None

    class Config:
        from_attributes = True

class EngagementAssignmentCreate(BaseModel):
    user_id: str
    role_id: Optional[str] = None
