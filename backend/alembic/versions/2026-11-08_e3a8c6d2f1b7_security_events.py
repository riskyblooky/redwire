"""Security Center tables — security_events, http_requests, http_traffic_hourly, http_log_cursors

Revision ID: e3a8c6d2f1b7
Revises: d1f7b3a9c2e4
Create Date: 2026-11-08
"""
from alembic import op
import sqlalchemy as sa

revision = "e3a8c6d2f1b7"
down_revision = "d1f7b3a9c2e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "security_events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("outcome", sa.String(10), nullable=False, server_default="info"),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("username", sa.String(255), nullable=True),
        sa.Column("actor_id", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
    )
    op.create_index("ix_security_events_created_at", "security_events", ["created_at"])
    op.create_index("ix_security_events_type_created", "security_events", ["event_type", "created_at"])
    op.create_index("ix_security_events_ip_created", "security_events", ["ip", "created_at"])
    op.create_index("ix_security_events_user_created", "security_events", ["user_id", "created_at"])

    op.create_table(
        "http_requests",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("ts", sa.DateTime(), nullable=False),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("method", sa.String(16), nullable=True),
        sa.Column("path", sa.String(1000), nullable=True),
        sa.Column("status", sa.Integer(), nullable=False),
        sa.Column("bytes", sa.BigInteger(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("host", sa.String(255), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("referer", sa.String(500), nullable=True),
        sa.Column("area", sa.String(8), nullable=True),
        sa.Column("flags", sa.String(100), nullable=True),
    )
    op.create_index("ix_http_requests_ts", "http_requests", ["ts"])
    op.create_index("ix_http_requests_ip_ts", "http_requests", ["ip", "ts"])
    op.create_index("ix_http_requests_status_ts", "http_requests", ["status", "ts"])

    op.create_table(
        "http_traffic_hourly",
        sa.Column("bucket", sa.DateTime(), primary_key=True),
        *[sa.Column(c, sa.Integer(), nullable=False, server_default="0")
          for c in ("requests", "s2xx", "s3xx", "s4xx", "s5xx", "s429", "probes", "scanner")],
    )

    op.create_table(
        "http_log_cursors",
        sa.Column("name", sa.String(50), primary_key=True),
        sa.Column("inode", sa.BigInteger(), nullable=True),
        sa.Column("offset", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("http_log_cursors")
    op.drop_table("http_traffic_hourly")
    op.drop_table("http_requests")
    op.drop_table("security_events")
