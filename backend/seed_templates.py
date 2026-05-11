import asyncio
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from database import AsyncSessionLocal, engine
from models.finding_template import FindingTemplate
from models.user import User, UserRole
from sqlalchemy import select

finding_templates = [
    {
        "title": "SQL Injection",
        "category": "Injection",
        "description": "The application fails to properly sanitize user-supplied input before using it in a SQL query. This allows an attacker to manipulate the query structure, potentially leading to unauthorized data access, modification, or deletion.",
        "impact": "An attacker can bypass authentication, read sensitive data from the database, modify or delete records, and in some cases, gain administrative control over the database server.",
        "mitigations": "Use parameterized queries or prepared statements for all database interactions. Additionally, implement input validation and use the principle of least privilege for database accounts."
    },
    {
        "title": "Cross-Site Scripting (Reflected XSS)",
        "category": "Injection",
        "description": "The application includes untrusted user input in a web page without proper encoding or validation. A reflected XSS attack occurs when user-supplied data in an HTTP request is included immediately in the response without sanitization, allowing an attacker to execute malicious scripts in the victim's browser context.",
        "impact": "Attackers can steal session cookies, hijack user accounts, redirect users to malicious sites, deface the website, or perform actions on behalf of the victim.",
        "mitigations": "Implement context-aware output encoding (e.g., HTML entity encoding) for all user-supplied data rendered in HTML, JavaScript, CSS, or URL contexts. Deploy a strict Content Security Policy (CSP) to restrict script sources. Use HTTPOnly and Secure flags on session cookies."
    },
    {
        "title": "Stored Cross-Site Scripting (Stored XSS)",
        "category": "Injection",
        "description": "The application stores user-provided data (e.g., in a database, message forum, comment field, or profile) and later includes it in web pages served to other users without proper encoding or sanitization. Unlike reflected XSS, the malicious payload is permanently stored on the target server.",
        "impact": "Every user who views the affected page will have the malicious script executed in their browser. This leads to persistent session hijacking, credential theft, malware distribution, and potentially full account compromise across all users.",
        "mitigations": "Sanitize and encode all user input before storing it. Apply context-aware output encoding when rendering stored content. Implement a strict Content Security Policy (CSP). Validate input on both client and server side."
    },
    {
        "title": "Broken Access Control (IDOR)",
        "category": "Broken Access Control",
        "description": "An Insecure Direct Object Reference (IDOR) occurs when an application provides direct access to objects based on user-supplied input (such as database IDs, filenames, or keys) without verifying if the user has permission to access those objects. By modifying the reference value, an attacker can access resources belonging to other users.",
        "impact": "An attacker can access, modify, or delete data belonging to other users, potentially leading to unauthorized information disclosure, data tampering, and full compromise of user privacy and data integrity.",
        "mitigations": "Implement robust server-side access control checks for every request that involves fetching or modifying data by ID. Use indirect object references (e.g., mapped UUIDs) if possible. Enforce role-based access control (RBAC) consistently across all endpoints."
    },
    {
        "title": "Broken Authentication - Weak Password Policy",
        "category": "Authentication Failures",
        "description": "The application lacks a strong password policy, allowing users to choose simple, easily guessable passwords (e.g., 'password123', 'admin', '12345678'). The system does not enforce minimum complexity requirements such as length, character variety, or common password blocking.",
        "impact": "User accounts are highly vulnerable to brute-force, dictionary, and credential stuffing attacks. A single compromised account could lead to further lateral movement within the application and access to sensitive data.",
        "mitigations": "Enforce a complex password policy requiring minimum length (12+ characters), character variety (uppercase, lowercase, numbers, symbols). Block commonly used passwords using a blocklist. Implement account lockout and rate limiting after repeated failed attempts. Mandate multi-factor authentication (MFA)."
    },
    {
        "title": "Broken Authentication - Missing Multi-Factor Authentication",
        "category": "Authentication Failures",
        "description": "The application relies solely on single-factor authentication (username and password) to verify user identity. No multi-factor authentication (MFA) mechanism is available or enforced, leaving accounts vulnerable if credentials are compromised through phishing, credential stuffing, or data breaches.",
        "impact": "Compromised credentials provide direct, unrestricted access to user accounts. Administrative accounts without MFA represent a critical risk, as their compromise can lead to full application takeover, data exfiltration, and unauthorized configuration changes.",
        "mitigations": "Implement multi-factor authentication (MFA) using TOTP (Time-Based One-Time Password), hardware security keys (FIDO2/WebAuthn), or push notification-based verification. Enforce MFA for all administrative and privileged accounts. Allow users to enroll in MFA with clear setup guidance."
    },
    {
        "title": "Sensitive Data Exposure - Unencrypted Communication",
        "category": "Cryptographic Failures",
        "description": "The application or service communicates over unencrypted HTTP, allowing sensitive data (such as credentials, session tokens, personal information, or API keys) to be intercepted in transit by anyone with access to the network path.",
        "impact": "Data sent between the client and server can be captured via Man-in-the-Middle (MitM) attacks on shared networks (e.g., public Wi-Fi), leading to credential theft, session hijacking, and exposure of personally identifiable information (PII).",
        "mitigations": "Enforce HTTPS across the entire application using TLS 1.2 or higher. Implement HSTS (HTTP Strict Transport Security) with a long max-age to ensure browsers only connect via secure channels. Redirect all HTTP traffic to HTTPS. Use secure cipher suites and disable weak protocols."
    },
    {
        "title": "Security Misconfiguration - Default Credentials",
        "category": "Security Misconfiguration",
        "description": "The application, server, or infrastructure component uses default or well-known credentials that were not changed during deployment. Common examples include default admin panels (admin/admin), database servers (root with no password), and vendor-supplied equipment with published default passwords.",
        "impact": "An attacker can gain full administrative access to the affected component using publicly known default credentials. This often leads to complete system compromise, data exfiltration, and the ability to pivot to other connected systems.",
        "mitigations": "Change all default credentials immediately upon deployment. Implement automated configuration management to detect and alert on default credentials. Use unique, complex passwords for all administrative accounts. Conduct periodic security audits to identify misconfigured services."
    },
    {
        "title": "Security Misconfiguration - Verbose Error Messages",
        "category": "Security Misconfiguration",
        "description": "The application returns detailed error messages or stack traces to users when an error occurs. These messages disclose internal implementation details such as framework versions, database types, file paths, SQL queries, and internal IP addresses.",
        "impact": "Detailed error messages provide attackers with valuable reconnaissance information that can be used to craft targeted attacks. Knowledge of specific software versions helps identify known vulnerabilities, and exposed SQL queries can reveal database structure for injection attacks.",
        "mitigations": "Implement custom error pages that display generic, user-friendly messages. Log detailed error information server-side for debugging purposes. Disable debug mode and verbose error reporting in production environments. Use a centralized error handling mechanism."
    },
    {
        "title": "Cross-Site Request Forgery (CSRF)",
        "category": "Broken Access Control",
        "description": "The application does not implement adequate CSRF protections, allowing an attacker to craft malicious requests that are executed in the context of an authenticated user's session. When a victim visits a malicious page or clicks a crafted link, their browser automatically includes session cookies, causing the application to process the forged request as legitimate.",
        "impact": "An attacker can force authenticated users to perform unintended actions such as changing their email address, transferring funds, modifying account settings, or executing administrative functions without the user's knowledge or consent.",
        "mitigations": "Implement anti-CSRF tokens (synchronizer token pattern) on all state-changing requests. Use SameSite cookie attribute set to 'Strict' or 'Lax'. Verify the Origin and Referer headers on the server side. Require re-authentication for sensitive operations."
    },
    {
        "title": "Server-Side Request Forgery (SSRF)",
        "category": "Injection",
        "description": "The application fetches remote resources based on user-supplied URLs without adequate validation or restrictions. An attacker can manipulate the URL parameter to make the server send requests to unintended destinations, including internal services, cloud metadata endpoints, or other backend infrastructure not accessible from the internet.",
        "impact": "An attacker can scan and access internal services, read cloud instance metadata (potentially exposing IAM credentials), exfiltrate sensitive data from internal networks, or interact with internal APIs. In cloud environments, SSRF can lead to full account compromise via metadata service exploitation.",
        "mitigations": "Implement a strict allowlist of permitted domains and IP ranges. Block requests to internal/private IP ranges (10.x, 172.16.x, 192.168.x, 169.254.x). Disable unnecessary URL schemes (file://, gopher://). Use a dedicated network-isolated service for fetching remote resources."
    },
    {
        "title": "Insecure Deserialization",
        "category": "Software and Data Integrity Failures",
        "description": "The application deserializes untrusted data without proper validation, allowing an attacker to manipulate serialized objects to achieve unintended consequences. This is common in applications that use Java serialization, Python pickle, PHP unserialize, or .NET BinaryFormatter with user-controlled input.",
        "impact": "Exploitation can lead to remote code execution, privilege escalation, injection attacks, replay attacks, or denial of service. In the worst case, an attacker can gain complete control over the host system.",
        "mitigations": "Avoid deserializing data from untrusted sources. Use safer serialization formats like JSON. Implement integrity checks (e.g., digital signatures) on serialized data. Monitor and alert on deserialization exceptions. Use allowlists for permitted classes during deserialization."
    },
    {
        "title": "Using Components with Known Vulnerabilities",
        "category": "Vulnerable and Outdated Components",
        "description": "The application uses third-party libraries, frameworks, or components that contain known security vulnerabilities. Outdated software versions with published CVEs remain in production without patching, creating exploitable entry points for attackers.",
        "impact": "Depending on the vulnerability, impact ranges from information disclosure and denial of service to remote code execution and complete system compromise. Known vulnerabilities often have publicly available exploit code, significantly lowering the barrier for attackers.",
        "mitigations": "Maintain a software bill of materials (SBOM) for all components. Implement automated dependency scanning (e.g., Dependabot, Snyk, OWASP Dependency-Check). Establish a patch management process with defined SLAs for critical vulnerabilities. Remove unused dependencies."
    },
    {
        "title": "Insufficient Logging and Monitoring",
        "category": "Security Logging and Monitoring Failures",
        "description": "The application does not adequately log security-relevant events such as authentication attempts, access control failures, input validation failures, or administrative actions. Existing logs may lack sufficient detail, are not monitored, or are not retained for an appropriate period.",
        "impact": "Without proper logging and monitoring, security breaches go undetected for extended periods, allowing attackers to maintain persistent access, escalate privileges, and exfiltrate data. The average breach detection time is significantly increased, and incident response is severely hampered.",
        "mitigations": "Log all authentication events (successes and failures), access control decisions, input validation failures, and administrative actions. Include contextual information (timestamp, user, IP, action, resource). Implement centralized log management with real-time alerting. Establish log retention policies and conduct regular log reviews."
    },
]

async def seed_templates():
    async with AsyncSessionLocal() as db:
        # Get an admin user to be the creator
        result = await db.execute(select(User).where(User.role == UserRole.ADMIN).limit(1))
        admin = result.scalar_one_or_none()
        
        if not admin:
            print("❌ No admin user found. Please create an admin user first.")
            return

        print(f"🌱 Seeding {len(finding_templates)} finding templates...")
        
        for t_data in finding_templates:
            # Check if template already exists by title
            exists = await db.execute(select(FindingTemplate).where(FindingTemplate.title == t_data["title"]))
            if exists.scalar_one_or_none():
                print(f"⏩ Template '{t_data['title']}' already exists, skipping.")
                continue
                
            template = FindingTemplate(
                **t_data,
                created_by=admin.id
            )
            db.add(template)
            print(f"✅ Added: {t_data['title']}")
            
        await db.commit()
        print("🚀 Seeding completed successfully!")

if __name__ == "__main__":
    asyncio.run(seed_templates())
