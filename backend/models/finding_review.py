from sqlalchemy import Column, String, DateTime, ForeignKey, UniqueConstraint
from database import Base
from datetime import datetime
import uuid


class FindingReview(Base):
    """A peer review on a finding.

    One row per (finding, reviewer) — a reviewer's latest verdict, upserted. When
    peer review is enabled (AuthSetting PEER_REVIEW_REQUIRED), a finding needs at
    least PEER_REVIEW_MIN_APPROVALS distinct APPROVED reviews from non-authors
    before it can transition to VERIFIED (enforced in update_finding).

    status: "APPROVED" | "CHANGES_REQUESTED". A reviewer may never review their
    own finding (the author can't approve their own work — the two-person rule).
    Discussion happens in the finding's comment threads, not here, so a review is
    just the verdict.
    """
    __tablename__ = "finding_reviews"
    __table_args__ = (
        UniqueConstraint("finding_id", "reviewer_id", name="uq_finding_review_reviewer"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    finding_id = Column(String, ForeignKey("findings.id", ondelete="CASCADE"), nullable=False, index=True)
    reviewer_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(24), nullable=False)  # APPROVED | CHANGES_REQUESTED
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
