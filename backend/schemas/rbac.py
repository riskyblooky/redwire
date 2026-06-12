from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from schemas._field_limits import DESCRIPTION, NAME

# --- Group Schemas ---

class GroupBase(BaseModel):
    name: str = Field(..., max_length=NAME)
    description: Optional[str] = Field(None, max_length=DESCRIPTION)

class GroupCreate(GroupBase):
    pass

class GroupUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=NAME)
    description: Optional[str] = Field(None, max_length=DESCRIPTION)

class GroupResponse(GroupBase):
    id: str

    class Config:
        from_attributes = True

# --- EngagementRole Schemas ---

class EngagementRoleBase(BaseModel):
    name: str = Field(..., max_length=NAME)
    description: Optional[str] = Field(None, max_length=DESCRIPTION)

class EngagementRoleCreate(EngagementRoleBase):
    pass

class EngagementRoleUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=NAME)
    description: Optional[str] = Field(None, max_length=DESCRIPTION)

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
