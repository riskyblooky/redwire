"""
Seed script to generate test data for stress testing the UI.
Run with: docker-compose exec backend python seed_test_data.py
"""
import asyncio
from datetime import datetime, timedelta
import random
from sqlalchemy import select
from database import AsyncSessionLocal
from models.user import User
from models.engagement import Engagement, EngagementStatus
from models.finding import Finding, Severity, FindingStatus
from models.asset import Asset
from models.testcase import TestCase

# Sample data
FINDING_TITLES = [
    "SQL Injection in Login Form",
    "Cross-Site Scripting (XSS) in User Profile",
    "Insecure Direct Object Reference in API",
    "Missing Authentication on Admin Panel",
    "Broken Access Control in File Upload",
    "Server-Side Request Forgery (SSRF)",
    "XML External Entity (XXE) Injection",
    "Command Injection in System Tools",
    "Privilege Escalation via API Endpoint",
    "Information Disclosure in Error Messages",
    "Weak Password Policy",
    "Missing Rate Limiting on Login",
    "Insecure Deserialization",
    "Path Traversal in File Download",
    "Cross-Site Request Forgery (CSRF)",
    "Session Fixation Vulnerability",
    "Clickjacking on Sensitive Pages",
    "Insecure Cryptographic Storage",
    "Broken Authentication Flow",
    "Missing Security Headers",
    "Open Redirect Vulnerability",
    "Host Header Injection",
    "Business Logic Flaw in Payment",
    "Race Condition in Transaction Processing",
    "Memory Leak in API Service",
]

ASSET_NAMES = [
    "web-app-01.example.com",
    "api.example.com",
    "admin.example.com",
    "192.168.1.50",
    "192.168.1.51",
    "192.168.1.52",
    "db-server-01",
    "auth-service",
    "payment-gateway",
    "file-storage-s3",
]

TESTCASE_TITLES = [
    "Authentication Bypass Test",
    "SQL Injection Detection",
    "XSS Payload Execution",
    "CSRF Token Validation",
    "Session Management Test",
    "Authorization Check",
    "Input Validation Test",
    "API Rate Limiting Test",
    "File Upload Security Test",
    "Encryption Strength Test",
]

async def seed_data():
    async with AsyncSessionLocal() as db:
        # Get an existing user (assuming admin user exists)
        result = await db.execute(select(User).limit(1))
        user = result.scalar_one_or_none()
        
        if not user:
            print("No users found in database. Please create a user first.")
            return
        
        print(f"Using user: {user.username}")
        
        # Create a new engagement
        engagement = Engagement(
            name="Acme Corp Full Stack Penetration Test",
            description="Comprehensive security assessment of Acme Corporation's web application infrastructure, including frontend, backend APIs, and database systems. This engagement includes OWASP Top 10 testing, business logic analysis, and infrastructure security review.",
            start_date=datetime.utcnow() - timedelta(days=14),
            end_date=datetime.utcnow() + timedelta(days=16),
            status=EngagementStatus.IN_PROGRESS,
            created_by=user.id
        )
        db.add(engagement)
        await db.flush()
        
        print(f"Created engagement: {engagement.name}")
        
        # Create assets
        print("\nCreating assets...")
        assets = []
        for i, asset_name in enumerate(ASSET_NAMES):
            asset_type = random.choice(['IP Address', 'Domain', 'URL', 'Server', 'Network'])
            asset = Asset(
                name=asset_name,
                asset_type=asset_type,
                identifier=asset_name,  # Use name as identifier
                description=f"Target asset #{i+1} for penetration testing",
                engagement_id=engagement.id
            )
            db.add(asset)
            assets.append(asset)
        
        await db.flush()
        print(f"Created {len(assets)} assets")
        
        # Create findings with varying severities
        print("\nCreating findings...")
        severities = [
            Severity.CRITICAL,
            Severity.CRITICAL,
            Severity.HIGH,
            Severity.HIGH,
            Severity.HIGH,
            Severity.MEDIUM,
            Severity.MEDIUM,
            Severity.MEDIUM,
            Severity.MEDIUM,
            Severity.LOW,
            Severity.LOW,
            Severity.INFO,
        ]
        
        findings = []
        for i, title in enumerate(FINDING_TITLES):
            severity = severities[i % len(severities)]
            
            # Generate realistic description
            descriptions = [
                f"The application is vulnerable to {title.lower()}. This issue was identified during testing of {random.choice(ASSET_NAMES)}.",
                f"A {severity.value.lower()} severity vulnerability allowing {title.lower()} was discovered.",
                f"Security testing revealed {title.lower()} affecting user data confidentiality.",
            ]
            
            # Generate impact based on severity
            impacts = {
                Severity.CRITICAL: "Complete system compromise possible. Attackers can gain full control of the application and access all sensitive data.",
                Severity.HIGH: "Significant security risk. Unauthorized access to sensitive data or functionality is possible.",
                Severity.MEDIUM: "Moderate security risk. Limited unauthorized access or information disclosure is possible.",
                Severity.LOW: "Minor security concern. Limited impact on security posture.",
                Severity.INFO: "Informational finding. No direct security impact but represents a security best practice deviation.",
            }
            
            finding = Finding(
                title=title,
                description=random.choice(descriptions),
                severity=severity,
                status=random.choice([FindingStatus.OPEN, FindingStatus.OPEN, FindingStatus.OPEN, FindingStatus.VALIDATED]),
                impact=impacts[severity],
                recommendation=f"Implement proper input validation and security controls. Review and remediate the vulnerable code. Apply security patches and update frameworks to latest versions.",
                engagement_id=engagement.id,
                created_at=datetime.utcnow() - timedelta(days=random.randint(1, 14))
            )
            db.add(finding)
            findings.append(finding)
        
        await db.flush()
        print(f"Created {len(findings)} findings")
        
        # Create test cases
        print("\nCreating test cases...")
        categories = [
            'Reconnaissance',
            'Scanning',
            'Exploitation',
            'Post-Exploitation',
            'Privilege Escalation',
            'Persistence',
            'Lateral Movement',
            'Web Application',
            'Other',
        ]
        
        testcases = []
        for i, title in enumerate(TESTCASE_TITLES):
            category = categories[i % len(categories)]
            is_executed = random.choice([True, True, False])
            
            testcase = TestCase(
                title=title,
                description=f"Test case for validating {title.lower()} security controls",
                category=category,
                steps=f"1. Navigate to target endpoint\n2. Execute test payload\n3. Observe application behavior\n4. Document findings",
                expected_result="Application should properly validate input and reject malicious payloads",
                is_executed=is_executed,
                is_successful=random.choice([True, False]) if is_executed else None,
                notes=f"Executed on {random.choice(ASSET_NAMES)}" if is_executed else None,
                engagement_id=engagement.id
            )
            db.add(testcase)
            testcases.append(testcase)
        
        await db.flush()
        print(f"Created {len(testcases)} test cases")
        
        # Commit all changes
        await db.commit()
        
        print("\n" + "="*50)
        print("✅ Test data generation complete!")
        print("="*50)
        print(f"Engagement: {engagement.name}")
        print(f"Assets: {len(assets)}")
        print(f"Findings: {len(findings)}")
        print(f"  - Critical: {sum(1 for f in findings if f.severity == Severity.CRITICAL)}")
        print(f"  - High: {sum(1 for f in findings if f.severity == Severity.HIGH)}")
        print(f"  - Medium: {sum(1 for f in findings if f.severity == Severity.MEDIUM)}")
        print(f"  - Low: {sum(1 for f in findings if f.severity == Severity.LOW)}")
        print(f"  - Info: {sum(1 for f in findings if f.severity == Severity.INFO)}")
        print(f"Test Cases: {len(testcases)}")
        print(f"  - Executed: {sum(1 for tc in testcases if tc.is_executed)}")
        print(f"  - Pending: {sum(1 for tc in testcases if not tc.is_executed)}")

if __name__ == "__main__":
    asyncio.run(seed_data())
