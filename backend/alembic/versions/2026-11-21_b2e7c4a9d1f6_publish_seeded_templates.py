"""publish seeded finding / test case templates left as DRAFT

The default-data seeder created its templates without a status, so they
took the ORM default DRAFT and were visible only to the bootstrap admin
(installs seeded before the status column existed got PUBLISHED from its
server_default). Publishes the seeded templates nobody has touched:
still DRAFT, never submitted, and no updated_by (every edit and workflow
action sets it, unpublish included, so a seeded template an admin
unpublished stays a draft). Anything else stays as it is.

Revision ID: b2e7c4a9d1f6
Revises: a8d3f6c2e9b1
Create Date: 2026-11-21
"""
import sqlalchemy as sa
from alembic import op

revision = "b2e7c4a9d1f6"
down_revision = "a8d3f6c2e9b1"
branch_labels = None
depends_on = None

# Titles as seeded at this revision (seed_templates.py / seed_testcase_templates.py).
FINDING_TITLES = (
    'SQL Injection',
    'Cross-Site Scripting (Reflected XSS)',
    'Stored Cross-Site Scripting (Stored XSS)',
    'Broken Access Control (IDOR)',
    'Broken Authentication - Weak Password Policy',
    'Broken Authentication - Missing Multi-Factor Authentication',
    'Sensitive Data Exposure - Unencrypted Communication',
    'Security Misconfiguration - Default Credentials',
    'Security Misconfiguration - Verbose Error Messages',
    'Cross-Site Request Forgery (CSRF)',
    'Server-Side Request Forgery (SSRF)',
    'Insecure Deserialization',
    'Using Components with Known Vulnerabilities',
    'Insufficient Logging and Monitoring',
)
TESTCASE_TITLES = (
    'SQL Injection Probing',
    'Cross-Site Scripting (XSS) Testing',
    'Passive Reconnaissance (OSINT)',
    'Port Scanning and Service Discovery',
    'Local Privilege Escalation (Linux)',
    'Broken Access Control (IDOR) Testing',
    'Authentication Mechanism Testing',
    'CSRF Token Validation Testing',
    'Server-Side Request Forgery (SSRF) Testing',
    'Security Header Analysis',
    'Local Privilege Escalation (Windows)',
    'API Security Assessment',
    'Lateral Movement Testing',
    'Social Engineering - Phishing Simulation',
)


def upgrade() -> None:
    bind = op.get_bind()
    for table, titles in (("finding_templates", FINDING_TITLES), ("testcase_templates", TESTCASE_TITLES)):
        bind.execute(sa.text(
            f"UPDATE {table} SET status = 'PUBLISHED', published_at = now() at time zone 'utc' "  # noqa: S608 — constant
            "WHERE status = 'DRAFT' AND published_at IS NULL AND submitted_at IS NULL "
            "AND updated_by IS NULL "
            "AND title = ANY(:titles) "
            "AND created_by IN (SELECT id FROM users WHERE role = 'ADMIN')"
        ), {"titles": list(titles)})


def downgrade() -> None:
    # Can't tell which rows this published from ones published since.
    pass
