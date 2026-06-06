"""Shared schemas for the template draft/submit/publish workflow."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class TemplateRejectRequest(BaseModel):
    review_note: str = Field(..., min_length=1, max_length=2000)


class TemplateApproveRequest(BaseModel):
    """Optional body on the /approve endpoints.

    `expected_updated_at` lets the reviewer pin the approval to the exact
    row revision they read. Required on the reviewer-publish path
    (SUBMITTED → PUBLISHED) so a creator can't withdraw, swap content,
    re-submit, and ride the reviewer's pending click. Optional on the
    manager self-publish path (own DRAFT → PUBLISHED) where there is no
    second party and so no race to lose.

    GHSA-9cvp-w26m-49j9.
    """

    expected_updated_at: Optional[datetime] = None
