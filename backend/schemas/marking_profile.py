from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from datetime import datetime

from models.marking_profile import MarkingScheme, MarkingEnforcement


# Valid mark-placement anchors for images/tables.
VALID_ANCHORS = {
    "TOP_LEFT", "TOP_CENTER", "TOP_RIGHT",
    "BOTTOM_LEFT", "BOTTOM_CENTER", "BOTTOM_RIGHT",
    "CAPTION",
}


class MarkingLevel(BaseModel):
    """One rung of the classification ladder. `rank` drives all roll-up;
    higher = more sensitive."""
    abbreviation: str = Field(..., max_length=40)
    full_name: str = Field(..., max_length=120)
    rank: int
    banner_color: str = Field("#1E293B", max_length=9)
    text_color: str = Field("#FFFFFF", max_length=9)


def _validate_anchors(v: List[str]) -> List[str]:
    bad = [a for a in v if a not in VALID_ANCHORS]
    if bad:
        raise ValueError(f"Invalid mark anchor(s): {', '.join(bad)}")
    return v


class MarkingProfileCreate(BaseModel):
    name: str = Field(..., max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    scheme: MarkingScheme = MarkingScheme.IC_DOD
    levels: List[MarkingLevel] = []
    enforcement: MarkingEnforcement = MarkingEnforcement.WARN
    image_mark_anchors: List[str] = ["CAPTION"]
    table_mark_anchors: List[str] = ["CAPTION"]
    inline_portion_marks: Optional[bool] = None
    table_per_row_marks: bool = False
    stamp_images: bool = False
    show_legend: bool = True
    distribution_statement: Optional[str] = Field(None, max_length=2000)
    static_heading_marks: Optional[str] = Field(None, max_length=20)  # LOWEST | INHERIT
    is_default: bool = False

    @field_validator("image_mark_anchors", "table_mark_anchors")
    @classmethod
    def _check_anchors(cls, v):
        return _validate_anchors(v)


class MarkingProfileUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    scheme: Optional[MarkingScheme] = None
    levels: Optional[List[MarkingLevel]] = None
    enforcement: Optional[MarkingEnforcement] = None
    image_mark_anchors: Optional[List[str]] = None
    table_mark_anchors: Optional[List[str]] = None
    inline_portion_marks: Optional[bool] = None
    table_per_row_marks: Optional[bool] = None
    stamp_images: Optional[bool] = None
    show_legend: Optional[bool] = None
    distribution_statement: Optional[str] = Field(None, max_length=2000)
    static_heading_marks: Optional[str] = Field(None, max_length=20)
    is_default: Optional[bool] = None

    @field_validator("image_mark_anchors", "table_mark_anchors")
    @classmethod
    def _check_anchors(cls, v):
        return v if v is None else _validate_anchors(v)


class MarkingProfileResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    scheme: MarkingScheme
    levels: List[MarkingLevel]
    enforcement: MarkingEnforcement
    image_mark_anchors: List[str]
    table_mark_anchors: List[str]
    inline_portion_marks: Optional[bool] = None
    table_per_row_marks: bool
    stamp_images: bool
    show_legend: bool
    distribution_statement: Optional[str] = None
    static_heading_marks: Optional[str] = None
    is_default: bool
    is_builtin: bool
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str] = None
    updated_by: Optional[str] = None

    class Config:
        from_attributes = True
