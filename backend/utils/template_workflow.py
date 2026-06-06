"""Shared workflow guards for the template / testcase-template / runbook
approval routers (GHSA-9cvp-w26m-49j9).

These three resource families share an identical draft → submitted →
published state machine and an identical TOCTOU window on
``POST /{id}/approve``: a creator could submit, watch a reviewer open
the row, then withdraw and substitute the body before the reviewer
clicked approve. The helpers here are imported by all three routers so
the lockdown logic stays in one place.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import HTTPException, status

from models.template_status import TemplateStatus
from models.user import User
from schemas.template_workflow import TemplateApproveRequest


logger = logging.getLogger(__name__)


def enforce_approve_workflow(
    obj,
    current_user: User,
    payload: Optional[TemplateApproveRequest],
    resource_label: str,
) -> None:
    """Reject the two TOCTOU paths a reviewer's /approve click is exposed to.

    * Foreign DRAFT is never approvable — the documented self-publish path
      is caller-as-creator only. A reviewer clicking approve on someone
      else's DRAFT means the row was withdrawn out from under them.
    * SUBMITTED → PUBLISHED requires the reviewer to pin the revision they
      read via ``expected_updated_at``. A missing or mismatched value means
      the row mutated between the GET the reviewer read and the approve
      they clicked; refuse with 409 and ask them to re-review.

    Self-DRAFT approve (the documented manage-role self-publish path)
    needs no version pin — there is no second party to race.
    """
    if obj.status == TemplateStatus.DRAFT and obj.created_by != current_user.id:
        logger.warning(
            "Blocked foreign-DRAFT approve on %s %s by user %s",
            resource_label, obj.id, current_user.id,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot approve another user's draft. The submission must be in SUBMITTED state.",
        )
    if obj.status == TemplateStatus.SUBMITTED:
        expected = payload.expected_updated_at if payload else None
        if expected is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="expected_updated_at is required when approving a submitted item; capture it from the GET response you reviewed.",
            )
        # Normalize both sides to naive UTC — the DB column is naive and the
        # Pydantic-deserialized value may carry tz info from the client.
        current = (
            obj.updated_at.replace(tzinfo=None)
            if obj.updated_at and obj.updated_at.tzinfo
            else obj.updated_at
        )
        seen = expected.replace(tzinfo=None) if expected.tzinfo else expected
        if current != seen:
            logger.warning(
                "Blocked stale-revision approve on %s %s by user %s: current=%s reviewer-saw=%s",
                resource_label, obj.id, current_user.id, current, seen,
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This submission has been modified since you opened it. Please re-review before approving.",
            )
