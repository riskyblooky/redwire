from pydantic import BaseModel
from typing import Optional, List


# ── Skill Category ───────────────────────────────────────────────
class SkillCategoryCreate(BaseModel):
    name: str
    color: Optional[str] = "#6366f1"
    sort_order: Optional[int] = 0

class SkillCategoryUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None
    sort_order: Optional[int] = None

class SkillCategoryResponse(BaseModel):
    id: str
    name: str
    color: Optional[str]
    sort_order: int
    skills: List["SkillResponse"] = []

    class Config:
        from_attributes = True


# ── Skill ────────────────────────────────────────────────────────
class SkillCreate(BaseModel):
    category_id: str
    name: str
    description: Optional[str] = None
    sort_order: Optional[int] = 0

class SkillUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category_id: Optional[str] = None
    sort_order: Optional[int] = None

class SkillResponse(BaseModel):
    id: str
    category_id: str
    name: str
    description: Optional[str]
    sort_order: int

    class Config:
        from_attributes = True


# ── User Skill ───────────────────────────────────────────────────
class UserSkillSet(BaseModel):
    """Bulk-set user skills: list of {skill_id, level, target_level?}"""
    skill_id: str
    level: int  # 0-3
    target_level: Optional[int] = None  # if set, must equal level+1

class UserSkillResponse(BaseModel):
    skill_id: str
    skill_name: str
    category_id: str
    category_name: str
    level: int
    target_level: Optional[int] = None

    class Config:
        from_attributes = True


class UserFocusSummary(BaseModel):
    """A user's set of growth focus skills."""
    user_id: str
    full_name: Optional[str] = None
    username: str
    skill_ids: List[str]


class EngagementFocusFit(BaseModel):
    """Users whose focus skills overlap a given engagement's required skills."""
    engagement_id: str
    matches: List["FocusFitMatch"]


class FocusFitSkill(BaseModel):
    id: str
    name: str


class FocusFitMatch(BaseModel):
    user_id: str
    full_name: Optional[str] = None
    username: str
    profile_photo: Optional[str] = None
    matching_skills: List[FocusFitSkill]


EngagementFocusFit.model_rebuild()


# ── Engagement Skill ─────────────────────────────────────────────
class EngagementSkillSet(BaseModel):
    """Set required skill for engagement: {skill_id, min_level}"""
    skill_id: str
    min_level: int  # 1-3

class EngagementSkillResponse(BaseModel):
    skill_id: str
    skill_name: str
    category_id: str
    category_name: str
    min_level: int

    class Config:
        from_attributes = True


# Rebuild forward refs
SkillCategoryResponse.model_rebuild()
