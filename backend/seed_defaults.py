"""
seed_defaults.py — single entry point for everything we want present
on a fresh install.

Everything below is idempotent (existence-checked). The point is that an
operator running `docker compose up` for the first time gets:

  - tags
  - configurable types (asset/engagement/testcase/finding/etc. dropdowns)
  - skill taxonomy (categories + skills)
  - one default report theme
  - one default report layout template
  - finding templates + testcase templates

The function `seed_all_defaults()` is invoked from main.py's lifespan
right after the admin user and groups/roles are created. Re-runs on
subsequent startups are no-ops.

The bulk template content (`finding_templates` and `testcase_templates`)
still lives in the standalone `seed_templates.py` and
`seed_testcase_templates.py` files so they remain runnable on demand for
developers; this module just re-imports those dicts.
"""

import uuid
from typing import List, Tuple

from sqlalchemy import select, func as sa_func, distinct

from database import AsyncSessionLocal


# ── Tags ──────────────────────────────────────────────────────────────

_DEFAULT_TAGS = [
    {"name": "Vendor Vuln", "color": "#ef4444"},
    {"name": "CVE", "color": "#f97316"},
    {"name": "Zero Day", "color": "#7c3aed"},
    {"name": "Known Exploit", "color": "#dc2626"},
    {"name": "Patch Available", "color": "#10b981"},
    {"name": "Mitigation Available", "color": "#06b6d4"},
    {"name": "Lateral Movement", "color": "#6366f1"},
    {"name": "Data Exfiltration", "color": "#a855f7"},
    {"name": "Persistence", "color": "#ec4899"},
]


async def seed_tags() -> int:
    from models.finding import Tag
    added = 0
    async with AsyncSessionLocal() as db:
        for t in _DEFAULT_TAGS:
            res = await db.execute(select(Tag).where(Tag.name == t["name"]))
            if res.scalar_one_or_none() is None:
                db.add(Tag(**t))
                added += 1
        await db.commit()
    return added


# ── Configurable types ───────────────────────────────────────────────
#
# Single source of truth — replaces the two overlapping lists that
# previously lived in main.py (startup hook) and seed_permissions.py
# (`seed_default_configurable_types`). Names for `intel` and `infra`
# categories are intentionally uppercase to match the IntelItemType /
# InfraType enum values stored in the DB.

_DEFAULT_CONFIGURABLE_TYPES = [
    # Client
    {"category": "client", "name": "Organization", "description": "Top-level organization or company", "color": "#6366f1", "is_system": True, "sort_order": 0},
    {"category": "client", "name": "Team",         "description": "Team or department within an organization", "color": "#06b6d4", "sort_order": 1},
    {"category": "client", "name": "Product",      "description": "Product or service line", "color": "#f59e0b", "sort_order": 2},

    # Engagement
    {"category": "engagement", "name": "Internal Penetration Test", "color": "#3b82f6", "is_system": True, "sort_order": 0},
    {"category": "engagement", "name": "External Penetration Test", "color": "#ef4444", "is_system": True, "sort_order": 1},
    {"category": "engagement", "name": "Web Application Test",      "color": "#8b5cf6", "sort_order": 2},
    {"category": "engagement", "name": "Mobile Application Test",   "color": "#06b6d4", "sort_order": 3},
    {"category": "engagement", "name": "Wireless Assessment",       "color": "#f59e0b", "sort_order": 4},
    {"category": "engagement", "name": "Social Engineering",        "color": "#ec4899", "sort_order": 5},
    {"category": "engagement", "name": "Physical Security",         "color": "#78716c", "sort_order": 6},
    {"category": "engagement", "name": "Red Team",                  "color": "#dc2626", "sort_order": 7},
    {"category": "engagement", "name": "Purple Team",               "color": "#7c3aed", "sort_order": 8},
    {"category": "engagement", "name": "Other",                     "color": "#6b7280", "sort_order": 9},

    # Asset
    {"category": "asset", "name": "IP Address",  "color": "#3b82f6", "is_system": True, "sort_order": 0},
    {"category": "asset", "name": "Domain",      "color": "#06b6d4", "sort_order": 1},
    {"category": "asset", "name": "URL",         "color": "#8b5cf6", "sort_order": 2},
    {"category": "asset", "name": "Application", "color": "#f59e0b", "sort_order": 3},
    {"category": "asset", "name": "Server",      "color": "#10b981", "sort_order": 4},
    {"category": "asset", "name": "Network",     "color": "#ec4899", "sort_order": 5},
    {"category": "asset", "name": "Other",       "color": "#6b7280", "sort_order": 6},

    # Test case categories
    {"category": "testcase", "name": "Reconnaissance",        "color": "#3b82f6", "is_system": True, "sort_order": 0},
    {"category": "testcase", "name": "Scanning",              "color": "#06b6d4", "is_system": True, "sort_order": 1},
    {"category": "testcase", "name": "Exploitation",          "color": "#ef4444", "is_system": True, "sort_order": 2},
    {"category": "testcase", "name": "Post-Exploitation",     "color": "#f97316", "is_system": True, "sort_order": 3},
    {"category": "testcase", "name": "Privilege Escalation",  "color": "#a855f7", "is_system": True, "sort_order": 4},
    {"category": "testcase", "name": "Persistence",           "color": "#ec4899", "is_system": True, "sort_order": 5},
    {"category": "testcase", "name": "Lateral Movement",      "color": "#6366f1", "is_system": True, "sort_order": 6},
    {"category": "testcase", "name": "Web Application",       "color": "#14b8a6", "is_system": True, "sort_order": 7},
    {"category": "testcase", "name": "Social Engineering",    "color": "#f59e0b", "is_system": True, "sort_order": 8},
    {"category": "testcase", "name": "Physical",              "color": "#78716c", "is_system": True, "sort_order": 9},
    {"category": "testcase", "name": "Other",                 "color": "#6b7280", "sort_order": 10},

    # Finding categories (OWASP-aligned)
    {"category": "finding", "name": "Broken Access Control",                       "color": "#f97316", "sort_order": 0},
    {"category": "finding", "name": "Cryptographic Failures",                      "color": "#8b5cf6", "sort_order": 1},
    {"category": "finding", "name": "Injection",                                   "color": "#dc2626", "sort_order": 2},
    {"category": "finding", "name": "Security Misconfiguration",                   "color": "#f59e0b", "sort_order": 3},
    {"category": "finding", "name": "Authentication Failures",                     "color": "#ef4444", "sort_order": 4},
    {"category": "finding", "name": "Software and Data Integrity Failures",        "color": "#e11d48", "sort_order": 5},
    {"category": "finding", "name": "Security Logging and Monitoring Failures",    "color": "#0ea5e9", "sort_order": 6},
    {"category": "finding", "name": "Vulnerable and Outdated Components",          "color": "#a855f7", "sort_order": 7},
    {"category": "finding", "name": "Network Security",                            "color": "#06b6d4", "sort_order": 8},
    {"category": "finding", "name": "Web Application",                             "color": "#14b8a6", "sort_order": 9},
    {"category": "finding", "name": "Information Disclosure",                      "color": "#3b82f6", "sort_order": 10},
    {"category": "finding", "name": "Other",                                       "color": "#6b7280", "sort_order": 11},

    # Vault
    {"category": "vault", "name": "Credential", "color": "#ef4444", "is_system": True, "sort_order": 0},
    {"category": "vault", "name": "Key",        "color": "#f59e0b", "is_system": True, "sort_order": 1},
    {"category": "vault", "name": "File",       "color": "#3b82f6", "is_system": True, "sort_order": 2},
    {"category": "vault", "name": "Note",       "color": "#10b981", "is_system": True, "sort_order": 3},

    # Cleanup
    {"category": "cleanup", "name": "SSH Key",    "color": "#f59e0b", "sort_order": 0},
    {"category": "cleanup", "name": "File",       "color": "#3b82f6", "sort_order": 1},
    {"category": "cleanup", "name": "Account",    "color": "#ef4444", "sort_order": 2},
    {"category": "cleanup", "name": "Permission", "color": "#a855f7", "sort_order": 3},
    {"category": "cleanup", "name": "Backdoor",   "color": "#dc2626", "sort_order": 4},
    {"category": "cleanup", "name": "Implant",    "color": "#ec4899", "sort_order": 5},
    {"category": "cleanup", "name": "Other",      "color": "#6b7280", "sort_order": 6},

    # Intel — names match IntelItemType enum (uppercase)
    {"category": "intel", "name": "CVE",      "color": "#ef4444", "is_system": True, "sort_order": 0},
    {"category": "intel", "name": "ADVISORY", "color": "#f59e0b", "is_system": True, "sort_order": 1},
    {"category": "intel", "name": "ARTICLE",  "color": "#3b82f6", "sort_order": 2},
    {"category": "intel", "name": "EXPLOIT",  "color": "#f97316", "sort_order": 3},
    {"category": "intel", "name": "ZINE",     "color": "#a855f7", "sort_order": 4},
    {"category": "intel", "name": "OTHER",    "color": "#6b7280", "sort_order": 5},

    # Infra — names match InfraType enum (uppercase)
    {"category": "infra", "name": "VPS",        "color": "#3b82f6", "is_system": True, "sort_order": 0},
    {"category": "infra", "name": "C2",         "color": "#ef4444", "is_system": True, "sort_order": 1},
    {"category": "infra", "name": "REDIRECTOR", "color": "#f59e0b", "sort_order": 2},
    {"category": "infra", "name": "PROXY",      "color": "#a855f7", "sort_order": 3},
    {"category": "infra", "name": "PHISHING",   "color": "#f97316", "sort_order": 4},
    {"category": "infra", "name": "JUMPBOX",    "color": "#10b981", "sort_order": 5},
    {"category": "infra", "name": "OTHER",      "color": "#6b7280", "sort_order": 6},

    # Runbook (categories of runbooks for organisation)
    {"category": "runbook", "name": "External Pentest",   "color": "#ef4444", "sort_order": 0},
    {"category": "runbook", "name": "Internal Pentest",   "color": "#f97316", "sort_order": 1},
    {"category": "runbook", "name": "Web Application",    "color": "#3b82f6", "sort_order": 2},
    {"category": "runbook", "name": "Mobile Application", "color": "#22c55e", "sort_order": 3},
    {"category": "runbook", "name": "Red Team",           "color": "#dc2626", "sort_order": 4},
    {"category": "runbook", "name": "Social Engineering", "color": "#a855f7", "sort_order": 5},
    {"category": "runbook", "name": "Physical Security",  "color": "#ec4899", "sort_order": 6},
    {"category": "runbook", "name": "Wireless",           "color": "#14b8a6", "sort_order": 7},
    {"category": "runbook", "name": "Cloud",              "color": "#6366f1", "sort_order": 8},
    {"category": "runbook", "name": "Other",              "color": "#6b7280", "sort_order": 9},
]


async def seed_configurable_types() -> int:
    from models.configurable_type import ConfigurableType
    added = 0
    async with AsyncSessionLocal() as db:
        for ct in _DEFAULT_CONFIGURABLE_TYPES:
            res = await db.execute(
                select(ConfigurableType).where(
                    ConfigurableType.category == ct["category"],
                    ConfigurableType.name == ct["name"],
                )
            )
            if res.scalar_one_or_none() is None:
                db.add(ConfigurableType(**ct))
                added += 1
        await db.commit()
    return added


async def sync_template_categories_to_configurable_types() -> int:
    """Auto-add any template category that's referenced by an existing
    template but missing from configurable_types."""
    from models.configurable_type import ConfigurableType
    from models.finding_template import FindingTemplate
    from models.testcase_template import TestCaseTemplate

    synced = 0
    async with AsyncSessionLocal() as db:
        for tpl_model, ct_category in [(FindingTemplate, "finding"), (TestCaseTemplate, "testcase")]:
            res = await db.execute(
                select(distinct(tpl_model.category)).where(
                    tpl_model.category.isnot(None),
                    tpl_model.category != "",
                )
            )
            for tpl_cat in [row[0] for row in res.all()]:
                exists = await db.execute(
                    select(ConfigurableType).where(
                        ConfigurableType.category == ct_category,
                        ConfigurableType.name == tpl_cat,
                    )
                )
                if exists.scalar_one_or_none() is None:
                    next_order = (await db.execute(
                        select(sa_func.max(ConfigurableType.sort_order)).where(
                            ConfigurableType.category == ct_category
                        )
                    )).scalar() or 0
                    db.add(ConfigurableType(
                        category=ct_category, name=tpl_cat,
                        color="#6b7280", sort_order=next_order + 1,
                    ))
                    synced += 1
        await db.commit()
    return synced


# ── Skills taxonomy ──────────────────────────────────────────────────

_SKILL_TAXONOMY: List[Tuple[Tuple[str, str], List[str]]] = [
    (("Offensive", "#ef4444"), [
        "Web Application Testing",
        "Network Penetration Testing",
        "Wireless Security",
        "Social Engineering",
        "Physical Security",
        "Mobile Application Testing",
        "API Testing",
        "Red Team Operations",
    ]),
    (("Defensive", "#3b82f6"), [
        "Incident Response",
        "Threat Hunting",
        "SIEM / Log Analysis",
        "Malware Analysis",
        "Digital Forensics",
        "Blue Team Operations",
    ]),
    (("Cloud & Infrastructure", "#10b981"), [
        "AWS Security",
        "Azure Security",
        "GCP Security",
        "Kubernetes Security",
        "Container Security",
        "IaC Review (Terraform/CloudFormation)",
    ]),
    (("Compliance & GRC", "#f59e0b"), [
        "PCI DSS",
        "HIPAA",
        "SOC 2",
        "ISO 27001",
        "NIST Framework",
        "Risk Assessment",
    ]),
    (("Development & Scripting", "#8b5cf6"), [
        "Python",
        "Exploit Development",
        "Tool Development",
        "Reverse Engineering",
        "Scripting (Bash/PowerShell)",
        "C/C++",
    ]),
]


async def seed_skill_taxonomy() -> Tuple[int, int]:
    """Seed skill categories + skills if either table is empty.

    Returns (categories_added, skills_added). Skips entirely once at
    least one category exists so admins can curate without us
    re-introducing defaults.
    """
    from models.skill import Skill, SkillCategory
    cats_added = 0
    skills_added = 0
    async with AsyncSessionLocal() as db:
        existing = await db.execute(select(SkillCategory))
        if existing.scalars().first() is not None:
            return (0, 0)

        for idx, ((cat_name, cat_color), skill_names) in enumerate(_SKILL_TAXONOMY):
            cat = SkillCategory(name=cat_name, color=cat_color, sort_order=idx)
            db.add(cat)
            await db.flush()  # populate cat.id
            cats_added += 1
            for sidx, sname in enumerate(skill_names):
                db.add(Skill(category_id=cat.id, name=sname, sort_order=sidx))
                skills_added += 1
        await db.commit()
    return (cats_added, skills_added)


# ── Report theme ─────────────────────────────────────────────────────
#
# The PDF generator falls back to a hardcoded `_DEFAULTS` palette in
# utils/report_generator.py when no theme is selected. Seeding a default
# row gives operators a starting point they can clone or tweak in the UI.

_DEFAULT_REPORT_THEME = {
    "name": "RedWire Default",
    "description": "Dark-executive Red Team palette — clone and tweak from the Themes page.",
    "primary_color":      "#DC2626",
    "secondary_color":    "#1E293B",
    "header_text_color":  "#0F172A",
    "body_text_color":    "#334155",
    "table_header_bg":    "#1E293B",
    "table_header_text":  "#FFFFFF",
    "font_family":        "Helvetica",
    "font_size_body":     10,
    "font_size_heading":  16,
    "show_page_numbers":  True,
    "show_cover_page":    True,
    "cover_title":        "Red Team Assessment Report",
    "footer_text":        "CONFIDENTIAL",
    "page_size":          "letter",
    "is_default":         True,
}


async def seed_default_report_theme() -> bool:
    from models.report_theme import ReportTheme
    async with AsyncSessionLocal() as db:
        existing = await db.execute(select(ReportTheme))
        if existing.scalars().first() is not None:
            return False
        db.add(ReportTheme(id=str(uuid.uuid4()), **_DEFAULT_REPORT_THEME))
        await db.commit()
    return True


# ── Report layout template ──────────────────────────────────────────

_DEFAULT_LAYOUT_NAME = "Standard Pentest Report"
_DEFAULT_LAYOUT_SECTIONS = [
    {
        "section_type": "text",
        "title": "Executive Summary",
        "content": (
            "_Replace this placeholder with a high-level overview of the engagement, "
            "key findings, and overall risk posture suitable for a non-technical audience._\n\n"
            "- Engagement objective\n- Scope at a glance\n- Top risk themes\n- Overall posture rating"
        ),
        "sort_order": 0,
    },
    {
        "section_type": "text",
        "title": "Scope & Methodology",
        "content": (
            "## Scope\n_List in-scope assets and any explicit exclusions._\n\n"
            "## Methodology\n_Briefly outline the testing methodology, tools, and frameworks used "
            "(e.g. PTES, OWASP WSTG, MITRE ATT&CK)._"
        ),
        "sort_order": 1,
    },
    {
        "section_type": "findings",
        "title": "Findings",
        "content": "",
        "sort_order": 2,
    },
    {
        "section_type": "testcases",
        "title": "Test Cases Executed",
        "content": "",
        "sort_order": 3,
    },
    {
        "section_type": "cleanup_artifacts",
        "title": "Cleanup Artifacts",
        "content": "",
        "sort_order": 4,
    },
    {
        "section_type": "text",
        "title": "Conclusion",
        "content": (
            "_Summarise remediation priorities, recommended next steps, and any follow-up "
            "engagements (retests, focused reviews) the team should consider._"
        ),
        "sort_order": 5,
    },
]


async def seed_default_report_layout() -> bool:
    from models.report_layout_template import ReportLayoutTemplate, ReportLayoutTemplateSection
    async with AsyncSessionLocal() as db:
        existing = await db.execute(
            select(ReportLayoutTemplate).where(ReportLayoutTemplate.name == _DEFAULT_LAYOUT_NAME)
        )
        if existing.scalar_one_or_none() is not None:
            return False
        tpl = ReportLayoutTemplate(
            id=str(uuid.uuid4()),
            name=_DEFAULT_LAYOUT_NAME,
            description="A reasonable baseline layout. Clone from the Reporting Layouts page to customise per engagement.",
        )
        db.add(tpl)
        await db.flush()
        for s in _DEFAULT_LAYOUT_SECTIONS:
            db.add(ReportLayoutTemplateSection(
                id=str(uuid.uuid4()),
                template_id=tpl.id,
                section_type=s["section_type"],
                title=s["title"],
                content=s["content"],
                sort_order=s["sort_order"],
            ))
        await db.commit()
    return True


# ── Finding + testcase templates ────────────────────────────────────

async def _admin_id(db) -> str | None:
    """First admin user id, or None if no admin exists yet."""
    from models.user import User, UserRole
    res = await db.execute(select(User.id).where(User.role == UserRole.ADMIN).limit(1))
    return res.scalar_one_or_none()


async def seed_finding_templates() -> int:
    """Idempotent — only adds templates whose title isn't already present."""
    from seed_templates import finding_templates
    from models.finding_template import FindingTemplate

    async with AsyncSessionLocal() as db:
        admin_id = await _admin_id(db)
        if not admin_id:
            return 0  # admin seed must run first
        added = 0
        for t in finding_templates:
            exists = await db.execute(
                select(FindingTemplate).where(FindingTemplate.title == t["title"])
            )
            if exists.scalar_one_or_none() is None:
                db.add(FindingTemplate(**t, created_by=admin_id))
                added += 1
        await db.commit()
        return added


async def seed_testcase_templates() -> int:
    from seed_testcase_templates import testcase_templates
    from models.testcase_template import TestCaseTemplate

    async with AsyncSessionLocal() as db:
        admin_id = await _admin_id(db)
        if not admin_id:
            return 0
        added = 0
        for t in testcase_templates:
            exists = await db.execute(
                select(TestCaseTemplate).where(TestCaseTemplate.title == t["title"])
            )
            if exists.scalar_one_or_none() is None:
                db.add(TestCaseTemplate(**t, created_by=admin_id))
                added += 1
        await db.commit()
        return added


# ── Orchestrator ────────────────────────────────────────────────────

async def seed_all_defaults():
    """Run every seeder in dependency order. Each is idempotent."""
    tag_n = await seed_tags()
    if tag_n:
        print(f"[seed] tags: +{tag_n}")

    ct_n = await seed_configurable_types()
    if ct_n:
        print(f"[seed] configurable_types: +{ct_n}")

    syn_n = await sync_template_categories_to_configurable_types()
    if syn_n:
        print(f"[seed] template-category sync: +{syn_n}")

    cats, skills = await seed_skill_taxonomy()
    if cats:
        print(f"[seed] skill taxonomy: +{cats} categories, +{skills} skills")

    if await seed_default_report_theme():
        print("[seed] report theme: +1 (RedWire Default)")

    if await seed_default_report_layout():
        print(f"[seed] report layout: +1 ({_DEFAULT_LAYOUT_NAME})")

    fn = await seed_finding_templates()
    if fn:
        print(f"[seed] finding templates: +{fn}")

    tn = await seed_testcase_templates()
    if tn:
        print(f"[seed] testcase templates: +{tn}")
