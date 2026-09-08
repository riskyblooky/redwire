from sqlalchemy import Column, String, DateTime, ForeignKey, Index
from database import Base
from datetime import datetime
import uuid


class ActivityPing(Base):
    """Append-only 'this user was actively working on this resource at time T'.

    Written by the activity heartbeat (see routers/users.py) only while the user
    has a resource open and is genuinely interacting (visible tab + recent input),
    throttled per (user, resource). Unlike User.last_active (a single scalar), this
    carries resource context and is append-only, so consecutive pings per
    (user, resource) can be bucketed into edit sessions to estimate time-on-task
    (e.g. "time spent writing findings"). engagement_id is resolved server-side
    from the resource at ping time for per-engagement aggregation.

    Purely a metrics substrate — never surfaced per-named-user (the aggregator
    returns anonymised, cohort-gated totals). Retention/rollup is a follow-up.
    """
    __tablename__ = "activity_pings"
    __table_args__ = (
        # The aggregator scans by (resource_type, created_at) and per-user session
        # bucketing walks (user_id, created_at); index both access paths.
        Index("ix_activity_pings_rtype_created", "resource_type", "created_at"),
        Index("ix_activity_pings_user_created", "user_id", "created_at"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    engagement_id = Column(String, nullable=True, index=True)  # resolved from the resource
    resource_type = Column(String(20), nullable=False)         # "finding" | "testcase" | "asset" | "note"
    resource_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
