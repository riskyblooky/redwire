"""
Validation + coercion for user-defined custom field VALUES.

Each core entity (asset/testcase/finding/client) carries a ``custom_fields``
JSON dict keyed by ``CustomFieldDefinition.field_key``. On create/update the
router hands the submitted dict here; we validate it against the active
definitions for that entity type, coerce each value to its declared type, and
return a cleaned dict safe to persist. Unknown keys are dropped (so a field
deleted after a client rendered its form doesn't 400 the save).
"""
from __future__ import annotations

import datetime as _dt
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.custom_field_definition import CustomFieldDefinition, CustomFieldType


def _is_empty(v) -> bool:
    return v is None or v == "" or v == []


def _coerce_value(defn: CustomFieldDefinition, value):
    """Coerce/validate one value against its definition. Raises HTTPException
    (422) on invalid input. Returns the cleaned value (or None if empty)."""
    if _is_empty(value):
        return None

    ftype = defn.field_type
    label = defn.label

    if ftype in (CustomFieldType.TEXT.value, CustomFieldType.TEXTAREA.value):
        return str(value)

    if ftype == CustomFieldType.URL.value:
        s = str(value).strip()
        # Rendered as a clickable link on the detail view — only permit
        # http/https so a stored ``javascript:``/``data:`` URI can't fire.
        if not (s.startswith("http://") or s.startswith("https://")):
            raise HTTPException(422, f"'{label}' must be an http:// or https:// URL.")
        return s

    if ftype == CustomFieldType.NUMBER.value:
        try:
            f = float(value)
        except (TypeError, ValueError):
            raise HTTPException(422, f"'{label}' must be a number.")
        # Return an int when the value is integral so JSON stays tidy.
        return int(f) if f.is_integer() else f

    if ftype == CustomFieldType.BOOLEAN.value:
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("true", "t", "1", "yes", "y")

    if ftype == CustomFieldType.DATE.value:
        s = str(value).strip()
        try:
            # Accept full ISO datetimes too, but store the date part.
            _dt.date.fromisoformat(s[:10])
        except ValueError:
            raise HTTPException(422, f"'{label}' must be an ISO date (YYYY-MM-DD).")
        return s[:10]

    if ftype == CustomFieldType.SELECT.value:
        opts = defn.options or []
        s = str(value)
        if s not in opts:
            raise HTTPException(422, f"'{label}' must be one of: {', '.join(opts)}.")
        return s

    if ftype == CustomFieldType.MULTISELECT.value:
        if not isinstance(value, list):
            raise HTTPException(422, f"'{label}' must be a list of selections.")
        opts = set(defn.options or [])
        cleaned = []
        for item in value:
            s = str(item)
            if s not in opts:
                raise HTTPException(422, f"'{label}' has an invalid selection: {s}.")
            cleaned.append(s)
        return cleaned

    # Unknown type in the DB — treat as text rather than 500.
    return str(value)


async def get_active_definitions(
    entity_type: str, db: AsyncSession
) -> list[CustomFieldDefinition]:
    """Active definitions for an entity type, in display order."""
    result = await db.execute(
        select(CustomFieldDefinition)
        .where(
            CustomFieldDefinition.entity_type == entity_type,
            CustomFieldDefinition.is_active == True,  # noqa: E712
        )
        .order_by(CustomFieldDefinition.position, CustomFieldDefinition.created_at)
    )
    return list(result.scalars().all())


async def validate_custom_fields(
    entity_type: str,
    submitted: Optional[dict],
    db: AsyncSession,
    *,
    partial: bool = False,
) -> dict:
    """Validate a submitted custom_fields dict against the active definitions.

    ``partial`` (updates): only the keys present in ``submitted`` are
    validated, and 'required' is not enforced for absent keys — a partial
    update shouldn't fail because an unrelated required field wasn't resent.
    On create (``partial=False``) every required field must have a value.

    Returns the cleaned dict (unknown keys dropped). Raises HTTPException(422)
    on any invalid or missing-required value.
    """
    if submitted is None:
        submitted = {}
    if not isinstance(submitted, dict):
        raise HTTPException(422, "custom_fields must be an object.")

    defs = await get_active_definitions(entity_type, db)
    by_key = {d.field_key: d for d in defs}

    cleaned: dict = {}
    for key, defn in by_key.items():
        present = key in submitted
        if not present:
            if not partial and defn.required:
                raise HTTPException(422, f"'{defn.label}' is required.")
            continue
        value = _coerce_value(defn, submitted[key])
        if value is None:
            if not partial and defn.required:
                raise HTTPException(422, f"'{defn.label}' is required.")
            # Store nothing for a cleared optional field.
            continue
        cleaned[key] = value

    return cleaned
