"""Regression: finding response schemas must tolerate a NULL created_by.

``finding.created_by`` (and ``finding_template.created_by``) is
``ON DELETE SET NULL`` via AuditMixin, so a row whose creator was later
deleted holds ``created_by = None``. ``FindingResponse.created_by`` was typed
as a required non-null ``str``, so serializing such a row raised a
``ResponseValidationError`` — i.e. ``GET /findings/{id}`` returned 500 instead
of the finding. These pin that a null creator now serializes cleanly, and that
a normal (non-null) creator still round-trips.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from schemas.finding import FindingResponse, FindingTemplateResponse


def _finding_kwargs(**overrides):
    base = dict(
        id="finding-1",
        engagement_id="eng-1",
        status="OPEN",
        created_by="user-1",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        title="SQL injection in /login",
        description="Parameter is concatenated into the query.",
        severity="HIGH",
    )
    base.update(overrides)
    return base


def test_finding_response_accepts_null_created_by():
    resp = FindingResponse(**_finding_kwargs(created_by=None))
    assert resp.created_by is None
    # The rest of the payload is unaffected.
    assert resp.severity == "HIGH"
    assert resp.status == "OPEN"


def test_finding_response_still_accepts_a_real_creator():
    resp = FindingResponse(**_finding_kwargs(created_by="user-42"))
    assert resp.created_by == "user-42"


def test_finding_response_still_requires_the_genuinely_required_fields():
    # created_by going Optional must not loosen the truly-required fields.
    kwargs = _finding_kwargs()
    del kwargs["title"]
    with pytest.raises(ValidationError):
        FindingResponse(**kwargs)


def test_finding_template_response_accepts_null_created_by():
    resp = FindingTemplateResponse(
        id="tmpl-1",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        created_by=None,
        status="PUBLISHED",
        title="Reusable finding",
        description="Body.",
    )
    assert resp.created_by is None
