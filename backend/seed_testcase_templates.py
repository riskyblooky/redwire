import asyncio
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from database import AsyncSessionLocal, engine
from models.testcase_template import TestCaseTemplate
from models.user import User, UserRole
from sqlalchemy import select

testcase_templates = [
    {
        "title": "SQL Injection Probing",
        "category": "Exploitation",
        "description": "Probe for SQL injection vulnerabilities by injecting special characters and Boolean logic into application parameters.",
        "steps": "1. Identify all user-controllable input fields (GET/POST parameters, headers, cookies).\n2. Inject single quotes ('), double quotes (\"), semicolons (;), and comment sequences (--, #).\n3. Use Boolean-based payloads: `' AND 1=1 --` and `' AND 1=2 --`.\n4. Test for time-based blind injection: `' ; WAITFOR DELAY '0:0:5' --`.\n5. Observe responses for SQL errors, timing differences, or content changes.\n6. Use sqlmap to automate and confirm findings if manual testing indicates vulnerability.",
        "expected_result": "SQL error messages, timing anomalies, or content changes that confirm user input is being incorporated into SQL queries without proper sanitization."
    },
    {
        "title": "Cross-Site Scripting (XSS) Testing",
        "category": "Web Application",
        "description": "Test for Reflected and Stored XSS by injecting script payloads into input fields and observing if they execute in the browser.",
        "steps": "1. Identify all input fields that are reflected in responses or stored and later displayed.\n2. Inject basic payload: `<script>alert(document.domain)</script>`.\n3. If filtered, try bypasses: `<img src=x onerror=alert(1)>`, `<svg onload=alert(1)>`, `\"><script>alert(1)</script>`.\n4. Test for DOM-based XSS by reviewing client-side JavaScript for unsafe sinks (innerHTML, document.write, eval).\n5. Test different contexts: HTML body, HTML attributes, JavaScript strings, URL parameters.\n6. Verify if Content Security Policy (CSP) is enforced and whether it can be bypassed.",
        "expected_result": "The application should encode or sanitize all user input preventing script execution. If XSS is found, document the injection point, payload, and context."
    },
    {
        "title": "Passive Reconnaissance (OSINT)",
        "category": "Reconnaissance",
        "description": "Gather information about the target organization and infrastructure using publicly available resources without directly interacting with their systems.",
        "steps": "1. Perform WHOIS lookups on all target domain names to identify registrants, name servers, and IP ranges.\n2. Use DNS enumeration tools (dig, dnsenum, subfinder) to discover subdomains.\n3. Search public databases (Shodan, Censys, ZoomEye) for exposed services.\n4. Perform Google dorking to find sensitive files, login pages, and configuration exposures.\n5. Search social media (LinkedIn) to identify employees, their roles, and technology mentions.\n6. Search GitHub, GitLab, Pastebin, and other code-sharing sites for leaked credentials or source code.\n7. Check certificate transparency logs (crt.sh) for additional subdomains.",
        "expected_result": "A comprehensive profile including subdomains, IP ranges, employee lists, technology stacks, and any leaked or exposed sensitive information."
    },
    {
        "title": "Port Scanning and Service Discovery",
        "category": "Scanning",
        "description": "Identify open ports, running services, and their versions on target assets using active network scanning techniques.",
        "steps": "1. Run a fast initial scan: `nmap -sV -sC -T4 [target]`.\n2. Perform a full port scan: `nmap -p 1-65535 -sV [target]`.\n3. Run UDP scan on common ports: `nmap -sU --top-ports 100 [target]`.\n4. Banner grab on identified open services using ncat or curl.\n5. Run vulnerability scripts: `nmap --script vuln [target]`.\n6. Cross-reference service versions against known CVE databases.\n7. Document all findings with port, protocol, service, and version information.",
        "expected_result": "Complete map of open ports, service versions, operating system identification, and potential misconfigurations or known vulnerabilities."
    },
    {
        "title": "Local Privilege Escalation (Linux)",
        "category": "Privilege Escalation",
        "description": "Identify and exploit misconfigurations or vulnerabilities on a Linux system to escalate privileges from a low-privilege shell to root access.",
        "steps": "1. Run enumeration scripts (LinPEAS, linux-exploit-suggester, lse.sh).\n2. Check for SUID/SGID binaries: `find / -perm -u=s -type f 2>/dev/null`.\n3. Check sudo permissions: `sudo -l` (look for NOPASSWD entries and GTFOBins exploitables).\n4. Check for writable cron jobs: `ls -la /etc/cron* /var/spool/cron/`.\n5. Search for cleartext credentials: config files, .bash_history, .env files, database configs.\n6. Check for kernel exploits: `uname -a` and cross-reference with exploit databases.\n7. Look for Docker/container escape opportunities if running in a container.\n8. Check for capabilities: `getcap -r / 2>/dev/null`.",
        "expected_result": "Root-level access or identification of escalation paths. Document the specific misconfiguration or vulnerability exploited."
    },
    {
        "title": "Broken Access Control (IDOR) Testing",
        "category": "Web Application",
        "description": "Test for Insecure Direct Object References by manipulating object identifiers (IDs, filenames, keys) in API requests to access resources belonging to other users.",
        "steps": "1. Create two test accounts with different permission levels.\n2. Identify all API endpoints that reference objects by ID (e.g., /api/users/123, /api/orders/456).\n3. From Account A, capture valid request IDs.\n4. From Account B, attempt to access Account A's resources by modifying IDs in URLs, request bodies, and headers.\n5. Test both horizontal escalation (same role, different user) and vertical escalation (lower role accessing admin resources).\n6. Test with predictable IDs (sequential integers) and UUIDs.\n7. Check if the API returns data in bulk endpoints that should be filtered by user.",
        "expected_result": "All requests for unauthorized resources should return 403 Forbidden or 404 Not Found. No data belonging to other users should be disclosed."
    },
    {
        "title": "Authentication Mechanism Testing",
        "category": "Web Application",
        "description": "Evaluate the strength and security of the application's authentication mechanisms including password policies, session management, and multi-factor authentication.",
        "steps": "1. Test password policy enforcement: try weak passwords (123456, password, admin123).\n2. Test account lockout: attempt 10+ failed logins and verify lockout/rate limiting behavior.\n3. Test credential stuffing resistance: use a list of common credentials against the login endpoint.\n4. Verify session token generation: check for randomness, length, and entropy.\n5. Test session fixation: check if session tokens change after successful login.\n6. Test remember-me functionality for security implications.\n7. Verify logout functionality properly invalidates the session server-side.\n8. Check for username enumeration via login error messages or timing differences.\n9. Test password reset flow for weaknesses (predictable tokens, no expiration).",
        "expected_result": "Strong password policy enforced, account lockout after failed attempts, secure session management, no username enumeration, and secure password reset flow."
    },
    {
        "title": "CSRF Token Validation Testing",
        "category": "Web Application",
        "description": "Test whether the application properly implements Cross-Site Request Forgery (CSRF) protections on all state-changing operations.",
        "steps": "1. Identify all state-changing requests (POST, PUT, DELETE, PATCH).\n2. Check if CSRF tokens are present in forms and AJAX requests.\n3. Remove the CSRF token from a request and verify the server rejects it.\n4. Reuse an old/expired CSRF token and verify it is rejected.\n5. Use a CSRF token from a different user session and verify it is rejected.\n6. Test if the SameSite cookie attribute is set on session cookies.\n7. Check if CORS policy properly restricts cross-origin requests.\n8. Craft a proof-of-concept HTML page that submits a forged request to verify exploitability.",
        "expected_result": "All state-changing requests should require and validate a CSRF token. Requests with missing, expired, or invalid tokens should be rejected."
    },
    {
        "title": "Server-Side Request Forgery (SSRF) Testing",
        "category": "Exploitation",
        "description": "Test for SSRF vulnerabilities by manipulating URL parameters that cause the server to make requests to attacker-controlled or internal destinations.",
        "steps": "1. Identify all features that accept URLs or fetch remote resources (webhooks, URL previews, file imports, PDF generators).\n2. Supply a Burp Collaborator or webhook.site URL to detect out-of-band interactions.\n3. Attempt to access internal services: `http://127.0.0.1`, `http://localhost`, `http://[::1]`.\n4. Test cloud metadata endpoints: `http://169.254.169.254/latest/meta-data/` (AWS), `http://metadata.google.internal/` (GCP).\n5. Try URL scheme variations: `file:///etc/passwd`, `gopher://`, `dict://`.\n6. Attempt bypasses: IP encoding (decimal, hex, octal), DNS rebinding, URL redirects.\n7. Test internal port scanning by iterating through port numbers on internal IPs.",
        "expected_result": "The application should block requests to internal IP ranges, cloud metadata endpoints, and non-HTTP(S) schemes. All URL inputs should be validated against an allowlist."
    },
    {
        "title": "Security Header Analysis",
        "category": "Scanning",
        "description": "Analyze HTTP response headers for the presence and correct configuration of security headers that protect against common web attacks.",
        "steps": "1. Make requests to the application and capture response headers.\n2. Check for Content-Security-Policy (CSP) header and evaluate its strictness.\n3. Verify X-Content-Type-Options is set to 'nosniff'.\n4. Check X-Frame-Options is set to 'DENY' or 'SAMEORIGIN'.\n5. Verify Strict-Transport-Security (HSTS) is present with adequate max-age.\n6. Check for X-XSS-Protection header (legacy but still relevant).\n7. Verify Referrer-Policy is set to a restrictive value.\n8. Check Permissions-Policy header for feature restrictions.\n9. Verify Cache-Control headers prevent caching of sensitive data.\n10. Use tools like securityheaders.com for automated analysis.",
        "expected_result": "All recommended security headers should be present with appropriate values. Missing or misconfigured headers should be documented with their risk implications."
    },
    {
        "title": "Local Privilege Escalation (Windows)",
        "category": "Privilege Escalation",
        "description": "Identify and exploit misconfigurations or vulnerabilities on a Windows system to escalate privileges from a low-privilege user to SYSTEM or Administrator access.",
        "steps": "1. Run enumeration tools (WinPEAS, PowerUp, Seatbelt).\n2. Check for unquoted service paths: `wmic service get name,displayname,pathname,startmode`.\n3. Check for weak service permissions: `accesschk.exe -uwcqv *`.\n4. Look for stored credentials: `cmdkey /list`, registry hives, browser saved passwords.\n5. Check for AlwaysInstallElevated: `reg query HKLM\\SOFTWARE\\Policies\\...`.\n6. Look for writable scheduled tasks and startup programs.\n7. Test for token impersonation (Potato attacks) if running as a service account.\n8. Check for missing patches: `systeminfo` and cross-reference with exploit databases.",
        "expected_result": "SYSTEM or Administrator access, or identification of escalation paths with documented misconfigurations."
    },
    {
        "title": "API Security Assessment",
        "category": "Web Application",
        "description": "Assess the security posture of REST/GraphQL APIs including authentication, authorization, input validation, rate limiting, and data exposure.",
        "steps": "1. Map all API endpoints and their HTTP methods using documentation or traffic interception.\n2. Test authentication: access endpoints without tokens, with expired tokens, with tokens from other users.\n3. Test authorization: access admin-only endpoints with regular user tokens.\n4. Test input validation: send oversized payloads, special characters, unexpected data types.\n5. Check for mass assignment: include unexpected fields in POST/PUT requests.\n6. Test rate limiting: send rapid automated requests to detect throttling.\n7. Check for excessive data exposure: compare API responses with what the UI displays.\n8. Test GraphQL for introspection, batching attacks, and nested query DoS.\n9. Verify proper error handling: errors should not leak internal details.",
        "expected_result": "APIs should enforce authentication and authorization on all endpoints, validate all input, rate limit requests, and return only necessary data. No internal details should be leaked."
    },
    {
        "title": "Lateral Movement Testing",
        "category": "Lateral Movement",
        "description": "After gaining initial access, attempt to move laterally through the network to access additional systems and resources using compromised credentials or session tokens.",
        "steps": "1. Enumerate the internal network: `arp -a`, `net view`, internal DNS records.\n2. Identify accessible network shares: `net share`, `smbclient -L`.\n3. Test credential reuse across discovered services (SSH, RDP, SMB, databases).\n4. Attempt pass-the-hash or pass-the-ticket attacks if Windows hashes/tickets are obtained.\n5. Check for accessible management interfaces (vCenter, iLO, IPMI, Jenkins).\n6. Test pivoting through compromised hosts to reach segmented networks.\n7. Look for internal web applications and services without authentication.\n8. Document all systems accessed and the path taken.",
        "expected_result": "Document the extent of lateral movement possible. Network segmentation should limit movement. Credential reuse and lack of segmentation should be reported as findings."
    },
    {
        "title": "Social Engineering - Phishing Simulation",
        "category": "Social Engineering",
        "description": "Conduct a controlled phishing simulation to assess the organization's susceptibility to email-based social engineering attacks and evaluate the effectiveness of security awareness training.",
        "steps": "1. Define scope and rules of engagement with the client (number of targets, allowed techniques).\n2. Gather target email addresses from OSINT or client-provided list.\n3. Register a convincing lookalike domain for the phishing campaign.\n4. Create a realistic phishing email template (e.g., password reset, IT notification).\n5. Set up a landing page to capture credentials (GoPhish or similar).\n6. Send phishing emails in batches and track opens, clicks, and submissions.\n7. Record metrics: email open rate, link click rate, credential submission rate.\n8. Verify if any users reported the phishing email to IT/security.\n9. Compile results and provide targeted recommendations.",
        "expected_result": "Report on click-through and credential submission rates. Identify users who need additional security awareness training. Evaluate effectiveness of email security controls (SPF, DKIM, DMARC)."
    },
]

async def seed_testcase_templates():
    async with AsyncSessionLocal() as db:
        # Get an admin user to be the creator
        result = await db.execute(select(User).where(User.role == UserRole.ADMIN).limit(1))
        admin = result.scalar_one_or_none()
        
        if not admin:
            print("❌ No admin user found. Please create an admin user first.")
            return

        print(f"🌱 Seeding {len(testcase_templates)} test case templates...")
        
        for t_data in testcase_templates:
            # Check if template already exists by title
            exists = await db.execute(select(TestCaseTemplate).where(TestCaseTemplate.title == t_data["title"]))
            if exists.scalar_one_or_none():
                print(f"⏩ Template '{t_data['title']}' already exists, skipping.")
                continue
                
            template = TestCaseTemplate(
                **t_data,
                created_by=admin.id
            )
            db.add(template)
            print(f"✅ Added: {t_data['title']}")
            
        await db.commit()
        print("🚀 Seeding completed successfully!")

if __name__ == "__main__":
    asyncio.run(seed_testcase_templates())
