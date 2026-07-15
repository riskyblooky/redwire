"""
Custom Field Definitions — admin-managed schema for user-defined fields on
core entities (assets, testcases, findings, clients).

A definition describes ONE custom field for ONE entity type: its key, label,
type, options, etc. The actual VALUES live in a ``custom_fields`` JSON column
on each entity row (keyed by ``field_key``), so values travel with the entity
(exports, cascade-on-delete) and need no polymorphic join table. This
definitions table drives the admin UI, server-side validation, and generic
rendering on the forms/detail views.
"""

from sqlalchemy import Column, String, Boolean, Integer, JSON, Text, UniqueConstraint
from database import Base, AuditMixin
import uuid
import enum


class CustomFieldEntity(str, enum.Enum):
    ASSET = "asset"
    TESTCASE = "testcase"
    FINDING = "finding"
    CLIENT = "client"


class CustomFieldType(str, enum.Enum):
    TEXT = "text"
    TEXTAREA = "textarea"
    NUMBER = "number"
    DATE = "date"
    BOOLEAN = "boolean"
    SELECT = "select"          # single choice from `options`
    MULTISELECT = "multiselect"  # subset of `options`
    URL = "url"


# Entity types stored as plain strings (not a PG enum) so adding a fifth
# entity later needs no ALTER TYPE. Validated at the API boundary.
ENTITY_VALUES = tuple(e.value for e in CustomFieldEntity)
FIELD_TYPE_VALUES = tuple(t.value for t in CustomFieldType)
# Types whose values are constrained to `options`.
OPTION_TYPES = {CustomFieldType.SELECT.value, CustomFieldType.MULTISELECT.value}


class CustomFieldDefinition(Base, AuditMixin):
    __tablename__ = "custom_field_definitions"
    __table_args__ = (
        # A field key is unique within an entity type; the same key may be
        # reused across entity types (e.g. "owner" on both findings + assets).
        UniqueConstraint("entity_type", "field_key", name="uq_custom_field_entity_key"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_type = Column(String(20), nullable=False, index=True)  # CustomFieldEntity value
    # Stable slug stored as the key in each entity's custom_fields JSON.
    field_key = Column(String(64), nullable=False)
    label = Column(String(120), nullable=False)
    field_type = Column(String(20), nullable=False, default="text")  # CustomFieldType value
    # For select / multiselect: list of allowed string options.
    options = Column(JSON, nullable=True, default=list)
    required = Column(Boolean, nullable=False, default=False)
    help_text = Column(Text, nullable=True)
    placeholder = Column(String(200), nullable=True)
    position = Column(Integer, nullable=False, default=0)  # display order, ascending
    # Opt this field into the entity's list/table view as a column (Phase 2).
    show_in_list = Column(Boolean, nullable=False, default=False)
    # Render this field's value in generated reports (Phase 3).
    show_in_report = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)
