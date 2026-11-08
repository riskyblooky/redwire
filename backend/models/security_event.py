from sqlalchemy import Column, String, DateTime, ForeignKey, Index, JSON, Integer, BigInteger
from database import Base
from datetime import datetime
import uuid


class SecurityEvent(Base):
    """Append-only record of security-relevant events for the admin Security
    Center: sign-ins (success / failure + reason), MFA, password and session
    changes, API tokens, account changes, rate-limit hits, SSO errors.

    Written by utils/security_events.record_security_event in its own session,
    so failed attempts (whose request transaction rolls back with the 401) are
    still kept. ``username`` is what was typed — it may not match any user.
    Pruned by retention (see utils/security_events.prune).
    """
    __tablename__ = "security_events"
    __table_args__ = (
        Index("ix_security_events_type_created", "event_type", "created_at"),
        Index("ix_security_events_ip_created", "ip", "created_at"),
        Index("ix_security_events_user_created", "user_id", "created_at"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    event_type = Column(String(50), nullable=False)
    outcome = Column(String(10), nullable=False, default="info")  # success | failure | info
    user_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    username = Column(String(255), nullable=True)
    actor_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)  # who did it, when not the subject
    ip = Column(String(64), nullable=True)
    user_agent = Column(String(500), nullable=True)
    reason = Column(String(255), nullable=True)
    details = Column(JSON, nullable=True)


class HttpRequestLog(Base):
    """One nginx access-log line (every request that reached the site, web and
    API alike), ingested from nginx's JSON log by utils/http_log_ingest.
    Short retention (default 14 days); long-range numbers come from
    HttpTrafficHourly. ``path`` is the path the client sent with the query
    string stripped (nginx.conf's $request_path), so a token-in-URL never
    lands here.
    """
    __tablename__ = "http_requests"
    __table_args__ = (
        Index("ix_http_requests_ip_ts", "ip", "ts"),
        Index("ix_http_requests_status_ts", "status", "ts"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    ts = Column(DateTime, nullable=False, index=True)
    ip = Column(String(64), nullable=True)
    method = Column(String(16), nullable=True)
    path = Column(String(1000), nullable=True)
    status = Column(Integer, nullable=False)
    bytes = Column(BigInteger, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    host = Column(String(255), nullable=True)
    user_agent = Column(String(500), nullable=True)
    referer = Column(String(500), nullable=True)
    area = Column(String(8), nullable=True)  # api | ws | web
    flags = Column(String(100), nullable=True)  # comma list: probe, scanner_ua, tool_ua


class HttpTrafficHourly(Base):
    """Hourly request counts, kept for a year after the raw lines are pruned."""
    __tablename__ = "http_traffic_hourly"

    bucket = Column(DateTime, primary_key=True)  # hour start, UTC
    requests = Column(Integer, nullable=False, default=0)
    s2xx = Column(Integer, nullable=False, default=0)
    s3xx = Column(Integer, nullable=False, default=0)
    s4xx = Column(Integer, nullable=False, default=0)
    s5xx = Column(Integer, nullable=False, default=0)
    s429 = Column(Integer, nullable=False, default=0)
    probes = Column(Integer, nullable=False, default=0)
    scanner = Column(Integer, nullable=False, default=0)


class HttpLogCursor(Base):
    """Where the ingester is in each log file (survives restarts)."""
    __tablename__ = "http_log_cursors"

    name = Column(String(50), primary_key=True)
    inode = Column(BigInteger, nullable=True)
    offset = Column(BigInteger, nullable=False, default=0)
    updated_at = Column(DateTime, nullable=True)
