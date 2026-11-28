"""Golden-file tests for report output. One representative engagement (every
section type, findings at each severity with markdown, custom fields and
per-item marks, a test case tree, cleanup items) is rendered under two
marking setups (an IC/DoD ladder with inline portion marks and a ceiling,
and TLP 2.0) plus unmarked. The HTML and Markdown documents are compared with
checked-in goldens under tests/fixtures/reports, so a change to wording,
order, escaping or a portion mark shows up as a diff to review.

The PDF isn't byte-stable across ReportLab versions, so it gets the marking
contract instead: the banner on every page (top and bottom for IC/DoD, top
only for TLP) and the portion marks in the text.

After an intended change:  UPDATE_GOLDEN=1 python -m pytest tests/test_report_golden.py
"""

from __future__ import annotations

import json
import os
import re
import zlib
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from models.report_layout import SectionType

GOLDEN = Path(__file__).parent / "fixtures" / "reports"
UPDATE = os.getenv("UPDATE_GOLDEN") == "1"
FIXED_NOW = datetime(2026, 11, 28, 9, 30, 0)

IC_LEVELS = [
    {"abbreviation": "U", "rank": 0, "full_name": "UNCLASSIFIED", "banner_color": "#007A33", "text_color": "#FFFFFF"},
    {"abbreviation": "C", "rank": 1, "full_name": "CONFIDENTIAL", "banner_color": "#0033A0", "text_color": "#FFFFFF"},
    {"abbreviation": "S", "rank": 2, "full_name": "SECRET", "banner_color": "#C8102E", "text_color": "#FFFFFF"},
    {"abbreviation": "TS", "rank": 3, "full_name": "TOP SECRET", "banner_color": "#FF8C00", "text_color": "#000000"},
]
TLP_LEVELS = [
    {"abbreviation": "CLEAR", "rank": 0, "banner_color": "#FFFFFF", "text_color": "#000000"},
    {"abbreviation": "GREEN", "rank": 1, "banner_color": "#33FF00", "text_color": "#000000"},
    {"abbreviation": "AMBER", "rank": 2, "banner_color": "#FFC000", "text_color": "#000000"},
    {"abbreviation": "RED", "rank": 3, "banner_color": "#FF0033", "text_color": "#FFFFFF"},
]


def _profile(scheme, levels, **over):
    base = dict(scheme=scheme, levels=levels, inline_portion_marks=True, static_heading_marks=None,
                image_mark_anchors=[], table_mark_anchors=[], table_per_row_marks=False,
                stamp_images=False, show_legend=True, distribution_statement="Distribution limited to the client.")
    base.update(over)
    return SimpleNamespace(**base)


PROFILES = {
    "unmarked": None,
    "ic": _profile("IC_DOD", IC_LEVELS),
    "tlp": _profile("TLP_2_0", TLP_LEVELS, distribution_statement=None),
}
# Per-scheme item levels: (engagement default, ceiling, high finding, info finding, test case, section)
LEVELS = {
    "unmarked": (None, None, None, None, None, None),
    "ic": ("C", "S", "TS", "U", "U", "S"),     # TS clamps to the S ceiling
    "tlp": ("GREEN", None, "AMBER", "CLEAR", "CLEAR", "AMBER"),
}


def _ns(**kw):
    return SimpleNamespace(**kw)


def _build(scheme):
    default, ceiling, hi, info, tc_level, sec_level = LEVELS[scheme]
    eng = _ns(id="e-1", name="Op Nightfall", client_name="ACME <Corp>", default_classification_level=default,
              default_classification_suffix=None, ceiling_classification_level=ceiling)
    web, dc = _ns(id="a-1", name="portal.acme.test"), _ns(id="a-2", name="dc01")

    def finding(fid, title, severity, **over):
        base = dict(id=fid, title=title, severity=severity, status="OPEN", category=None, score_model=None,
                    score_inputs=None, cvss_score=None, cvss_vector=None, description="", impact="",
                    steps_to_reproduce="", technical_details="", mitigations="", references="",
                    custom_fields={}, assets=[], evidence=[], classification_level=None, classification_suffix=None)
        base.update(over)
        return _ns(**base)

    findings = [
        finding("f-3", "Verbose server banner", "INFO", status="REMEDIATED", assets=[web], classification_level=info,
                description="The `Server` header discloses *nginx 1.24.0*."),
        finding("f-1", "SQL injection in search", "CRITICAL", category="Injection", assets=[web, dc],
                cvss_score=9.8, cvss_vector="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
                description="The **q** parameter is concatenated into SQL.\n\n- union-based\n- time-based",
                impact="Full read of the `users` table.", steps_to_reproduce="1. Send `q='`\n2. Observe the error",
                technical_details="```sql\nSELECT * FROM items WHERE name LIKE '%{q}%'\n```",
                mitigations="Use parameterised queries.", references="https://owasp.org/www-community/attacks/SQL_Injection",
                custom_fields={"ticket": "SEC-101"}, classification_level=hi),
        finding("f-2", "Kerberoastable service account <svc_sql>", "HIGH", status="VERIFIED", assets=[dc],
                description="SPN set on a user account with a weak password & no AES.", mitigations="Rotate to a gMSA."),
        finding("f-4", "SMB signing not required", "MEDIUM", assets=[dc], description="Relay is possible."),
        finding("f-5", "Missing HSTS", "LOW", assets=[web], description="No `Strict-Transport-Security` header."),
    ]

    def tc(tid, title, parent=None, **over):
        base = dict(id=tid, title=title, parent_id=parent, category="Web", is_executed=False, is_successful=None,
                    description="", steps="", expected_result="", actual_result="", notes="", assets=[],
                    findings=[], classification_level=None, classification_suffix=None)
        base.update(over)
        return _ns(**base)

    testcases = [
        tc("t-2", "SQLi in search", parent="t-1", is_executed=True, is_successful=True, steps="Fuzz `q`",
           findings=[findings[1]], classification_level=tc_level),
        tc("t-1", "Input validation", is_executed=True, is_successful=False),
        tc("t-3", "Kerberoasting", category="AD", description="Request TGS for SPN accounts."),
    ]
    cleanup = [
        _ns(id="c-1", title="Implant on dc01", artifact_type="FILE", status="PENDING", location="C:\\Windows\\Temp\\a.exe",
            description="Beacon dropped during lateral movement.", assets=[dc], findings=[], testcases=[],
            classification_level=None, classification_suffix=None, cleaned_at=None, cleaned_by=None, notes=None,
            cleanup_notes=None),
        _ns(id="c-2", title="Test account", artifact_type="ACCOUNT", status="CLEANED", location="CORP\\rw_test",
            description="Created for the spray.", assets=[], findings=[], testcases=[], classification_level=None,
            classification_suffix=None, cleaned_at=FIXED_NOW, cleaned_by=None, notes=None, cleanup_notes=None),
    ]

    def section(kind, title, content="", level=None):
        return _ns(section_type=kind, title=title, content=content, page_break_before=False,
                   classification_level=level, classification_suffix=None)

    sections = [
        section(SectionType.TEXT, "Executive Summary",
                "ACME engaged us for **two weeks**. <script>alert(1)</script> Key risks:\n\n1. Injection\n2. AD hygiene",
                level=sec_level),
        section(SectionType.FINDINGS, "Findings"),
        section(SectionType.TESTCASES, "Test Cases"),
        section(SectionType.CLEANUP_ARTIFACTS, "Cleanup"),
        section(SectionType.TEXT, "Appendix", "| Tool | Version |\n|---|---|\n| nmap | 7.94 |"),
    ]
    return dict(engagement=eng, sections=sections, findings=findings, testcases=testcases,
                cleanup_artifacts=cleanup, marking_profile=PROFILES[scheme])


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch):
    class _DT(datetime):
        @classmethod
        def now(cls, tz=None):
            return FIXED_NOW

    class _D(date):
        @classmethod
        def today(cls):
            return FIXED_NOW.date()
    import utils.reports.content as content
    import utils.reports.markdown_report as md
    import utils.reports.pdf.cover as cover
    monkeypatch.setattr(md, "datetime", _DT)
    monkeypatch.setattr(cover, "datetime", _DT)
    monkeypatch.setattr(content, "date", _D)


def _check(text: str, name: str):
    path = GOLDEN / name
    if UPDATE or not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        if not UPDATE:
            pytest.fail(f"wrote missing golden {name}; review it and re-run")
        return
    assert text == path.read_text(encoding="utf-8"), (
        f"{name} differs; if intended, regenerate with UPDATE_GOLDEN=1 and review the diff")


@pytest.mark.parametrize("scheme", sorted(PROFILES))
def test_markdown_matches_golden(scheme):
    from utils.reports import MarkdownReportGenerator
    _check(MarkdownReportGenerator(**_build(scheme)).generate(), f"report_{scheme}.md")


def _html_payload(html: str) -> dict:
    """The report data the interactive HTML viewer renders. The rest of the
    document is the fixed viewer template (report_templates/interactive)."""
    import json
    m = re.search(r"window\.__REPORT__ = (\{.*?\});\n", html)
    assert m, "payload not found in the HTML report"
    return json.loads(m.group(1))


@pytest.mark.parametrize("scheme", sorted(PROFILES))
def test_html_payload_matches_golden(scheme):
    import json
    from utils.reports import HTMLReportGenerator
    html = HTMLReportGenerator(**_build(scheme)).generate()
    _check(json.dumps(_html_payload(html), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
           f"report_{scheme}.html.json")


@pytest.mark.parametrize("hostile", ["</script><script>alert(1)</script>", "<!--<script>", "</SCRIPT >"])
def test_html_payload_cannot_leave_its_script_element(hostile):
    from utils.reports import HTMLReportGenerator
    built = _build("ic")
    built["findings"][0].title = hostile
    built["engagement"].client_name = hostile
    html = HTMLReportGenerator(**built).generate()
    start = html.index("window.__REPORT__")
    end = html.index(";\n", start)
    assert "<" not in html[start:end], "a raw '<' inside the payload"
    assert hostile in json.dumps(_html_payload(html), ensure_ascii=False), "the value still round-trips"


# ── PDF marking contract ────────────────────────────────────────────────

def _pdf_pages_text(pdf: bytes) -> list[str]:
    """Text drawn on each page, from the content streams (ReportLab writes
    one ASCII85 + Flate stream per page, in page order)."""
    import base64
    pages = []
    for m in re.finditer(rb"stream\r?\n(.*?)\s*endstream", pdf, re.DOTALL):
        raw = m.group(1).strip()
        try:
            if raw.endswith(b"~>"):
                raw = base64.a85decode(raw[:-2].removeprefix(b"<~"))
            data = zlib.decompress(raw)
        except (zlib.error, ValueError):
            continue
        if b" Tj" in data or b"TJ" in data:
            strings = re.findall(rb"\((.*?)(?<!\\)\)\s*Tj", data)
            pages.append(" ".join(re.sub(rb"\\([()\\])", rb"\1", t).decode("latin-1") for t in strings))
    return pages


@pytest.mark.parametrize("scheme,banner,marks", [
    # IC/DoD: a strip top and bottom; TLP: a chip in the header and footer.
    ("ic", "SECRET", {"SQL injection in search": "(S)", "Verbose server banner": "(U)",
                      "Kerberoastable service account": "(C)"}),
    ("tlp", "TLP:AMBER", {"SQL injection in search": "TLP:AMBER", "Verbose server banner": "TLP:CLEAR",
                          "Kerberoastable service account": "TLP:GREEN"}),
])
def test_pdf_banner_on_every_page_and_portion_marks(scheme, banner, marks):
    from utils.reports import PDFReportGenerator
    pages = _pdf_pages_text(PDFReportGenerator(**_build(scheme), theme=None, storage=None).generate())
    assert len(pages) >= 3, "the fixture spans several pages"
    for i, text in enumerate(pages, 1):
        assert text.count(banner) >= 2, f"page {i}: banner {banner!r} drawn {text.count(banner)}x"
    body = " ".join(pages)
    for title, mark in marks.items():
        assert re.search(rf"F\d\d\s+{re.escape(mark)}\s+{re.escape(title)}", body), (title, mark)
    assert "ACME engaged us for" in body and "<script>" not in body


def test_pdf_unmarked_has_no_banner():
    from utils.reports import PDFReportGenerator
    body = " ".join(_pdf_pages_text(PDFReportGenerator(**_build("unmarked"), theme=None, storage=None).generate()))
    assert "SQL injection in search" in body
    # (The theme's default footer says "CONFIDENTIAL"; that's not a marking.)
    assert not re.search(r"\bSECRET\b|UNCLASSIFIED|TLP:|\((U|C|S|TS)\)", body)
