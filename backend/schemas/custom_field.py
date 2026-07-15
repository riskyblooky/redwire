"""Pydantic schemas for custom field DEFINITIONS (the admin-managed schema).
Values live on each entity's ``custom_fields`` dict and are validated by
``utils/custom_fields.py``, not here."""
from typing import Optional, List
from pydantic import BaseModel, Field


class CustomFieldDefinitionBase(BaseModel):
    field_key: Optional[str] = Field(None, max_length=64)  # auto-slugged from label if omitted
    label: str = Field(..., min_length=1, max_length=120)
    field_type: str = Field("text", max_length=20)
    options: Optional[List[str]] = None
    required: bool = False
    help_text: Optional[str] = Field(None, max_length=2000)
    placeholder: Optional[str] = Field(None, max_length=200)
    position: Optional[int] = Field(None, ge=0)
    show_in_list: bool = False
    show_in_report: bool = False


class CustomFieldDefinitionCreate(CustomFieldDefinitionBase):
    pass


class CustomFieldDefinitionUpdate(BaseModel):
    label: Optional[str] = Field(None, min_length=1, max_length=120)
    field_type: Optional[str] = Field(None, max_length=20)
    options: Optional[List[str]] = None
    required: Optional[bool] = None
    help_text: Optional[str] = Field(None, max_length=2000)
    placeholder: Optional[str] = Field(None, max_length=200)
    position: Optional[int] = Field(None, ge=0)
    show_in_list: Optional[bool] = None
    show_in_report: Optional[bool] = None
    is_active: Optional[bool] = None


class CustomFieldDefinitionResponse(BaseModel):
    id: str
    entity_type: str
    field_key: str
    label: str
    field_type: str
    options: Optional[List[str]] = None
    required: bool
    help_text: Optional[str] = None
    placeholder: Optional[str] = None
    position: int
    show_in_list: bool
    show_in_report: bool
    is_active: bool

    class Config:
        from_attributes = True


class ReorderItem(BaseModel):
    id: str
    position: int = Field(..., ge=0)


class ReorderRequest(BaseModel):
    fields: List[ReorderItem] = Field(..., min_length=1)
