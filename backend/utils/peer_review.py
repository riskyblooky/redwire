"""Peer-review policy for findings.

Admin-configurable via the AuthSetting KV table:
  - PEER_REVIEW_REQUIRED     "true"/"false"  (default false)
  - PEER_REVIEW_MIN_APPROVALS integer string (default 2)

When required, a finding needs at least MIN_APPROVALS distinct APPROVED reviews
from users other than its author before it can transition to VERIFIED.
"""
from fastapi import HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

REQUIRED_KEY = "PEER_REVIEW_REQUIRED"
MIN_APPROVALS_KEY = "PEER_REVIEW_MIN_APPROVALS"
_DEFAULT_MIN = 2


async def get_peer_review_config(db: AsyncSession) -> tuple[bool, int]:
    """Return (required, min_approvals). Robust to unset/garbage values."""
    from models.auth_settings import AuthSetting
    rows = (await db.execute(
        select(AuthSetting).where(AuthSetting.key.in_([REQUIRED_KEY, MIN_APPROVALS_KEY]))
    )).scalars().all()
    vals = {r.key: (r.value or "") for r in rows}
    required = str(vals.get(REQUIRED_KEY, "")).strip().lower() == "true"
    try:
        min_approvals = int(str(vals.get(MIN_APPROVALS_KEY, "")).strip())
    except (TypeError, ValueError):
        min_approvals = _DEFAULT_MIN
    min_approvals = max(1, min(min_approvals, 20))
    return required, min_approvals


async def count_finding_approvals(db: AsyncSession, finding_id: str, exclude_user_id: str | None) -> int:
    """Distinct users who APPROVED this finding, excluding the author."""
    from models.finding_review import FindingReview
    q = select(func.count(func.distinct(FindingReview.reviewer_id))).where(
        FindingReview.finding_id == finding_id,
        FindingReview.status == "APPROVED",
    )
    if exclude_user_id:
        q = q.where(FindingReview.reviewer_id != exclude_user_id)
    return int((await db.execute(q)).scalar() or 0)


async def assert_finding_verifiable(db: AsyncSession, finding) -> None:
    """Raise 409 if peer review is required and this finding lacks enough
    non-author approvals to be marked VERIFIED. No-op when review isn't required.
    Applies to everyone — the point is to gate the verify action itself."""
    required, min_approvals = await get_peer_review_config(db)
    if not required:
        return
    approvals = await count_finding_approvals(db, finding.id, finding.created_by)
    if approvals < min_approvals:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Peer review required: this finding has {approvals} of "
                f"{min_approvals} required peer approval(s). Ask other operators "
                f"to review it before marking it VERIFIED."
            ),
        )
