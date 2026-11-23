"""utils/reports/content.py — the one report document every format renders.

The PDF, Markdown and interactive HTML renderers used to each decide order,
display ids, fields, statuses and portion marks for themselves, and drifted
(Markdown carried no marks or banner; technical details only reached the
HTML report; test-case ids differed between the PDF graph and its test-case
section). These tests pin the document and check the formats agree on it.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

from models.report_layout import SectionType
from utils.reports.content import build_report_document
from utils.reports import HTMLReportGenerator, MarkdownReportGenerator, PDFReportGenerator
from tests.test_report_generator import _payload


def _id():
    return str(uuid.uuid4())


def _finding(title, severity="HIGH", **over):
    base = dict(id=_id(), title=title, severity=severity, status="OPEN", category=None,
                score_model=None, score_inputs=None, cvss_score=None, cvss_vector=None,
                description="desc", impact="", steps_to_reproduce="", technical_details="",
                mitigations="", references="", custom_fields={}, assets=[], evidence=[],
                classification_level=None, classification_suffix=None)
    base.update(over)
    return SimpleNamespace(**base)


def _evidence(**over):
    base = dict(id=_id(), include_in_report=True, filename="k", mime_type="application/pdf",
                description="proof", original_filename="p.pdf",
                classification_level=None, classification_suffix=None)
    base.update(over)
    return SimpleNamespace(**base)


def _tc(title, parent_id=None, **over):
    base = dict(id=_id(), title=title, parent_id=parent_id, category="Web", is_executed=False,
                is_successful=None, description="", steps="", expected_result="", actual_result="",
                notes="", assets=[], findings=[], classification_level=None, classification_suffix=None)
    base.update(over)
    return SimpleNamespace(**base)


def _section(kind, title, level=None):
    return SimpleNamespace(section_type=kind, title=title, content="Body", page_break_before=False,
                           classification_level=level, classification_suffix=None)


def _engagement(default=None, ceiling=None):
    return SimpleNamespace(name="Op", client_name="ACME", default_classification_level=default,
                           default_classification_suffix=None, ceiling_classification_level=ceiling)


_LEVELS = [
    {"abbreviation": "U", "rank": 0, "full_name": "UNCLASSIFIED", "banner_color": "#007A33"},
    {"abbreviation": "C", "rank": 1, "full_name": "CONFIDENTIAL", "banner_color": "#0033A0"},
    {"abbreviation": "S", "rank": 2, "full_name": "SECRET", "banner_color": "#C8102E"},
    {"abbreviation": "TS", "rank": 3, "full_name": "TOP SECRET", "banner_color": "#FF8C00"},
]


def _profile(**over):
    base = dict(scheme="IC_DOD", levels=_LEVELS, inline_portion_marks=True, static_heading_marks=None,
                image_mark_anchors=[], table_mark_anchors=[], table_per_row_marks=False,
                stamp_images=False, show_legend=True, distribution_statement="Handle with care")
    base.update(over)
    return SimpleNamespace(**base)


_SECTIONS = [
    _section(SectionType.TEXT, "Intro"),
    _section(SectionType.FINDINGS, "Findings"),
    _section(SectionType.TESTCASES, "Tests"),
]


def test_findings_ordered_with_shared_ids_and_fields():
    low = _finding("Low one", "LOW", technical_details="tech")
    crit = _finding("Crit one", "CRITICAL", mitigations="fix it")
    doc = build_report_document(_engagement(), _SECTIONS, [low, crit], [])
    assert [(f.ref, f.title) for f in doc.findings] == [("F01", "Crit one"), ("F02", "Low one")]
    assert [(x.label, x.markdown) for x in doc.findings[1].fields] == [
        ("Description", "desc"), ("Technical Details", "tech")]
    assert ("Recommendations", "fix it") in [(x.label, x.markdown) for x in doc.findings[0].fields]
    assert doc.severity_counts["CRITICAL"] == 1 and doc.severity_counts["MEDIUM"] == 0


def test_testcases_are_a_tree_with_matching_refs():
    parent = _tc("Parent", category="Web", is_executed=True, is_successful=True)
    child = _tc("Child", parent_id=parent.id)
    other = _tc("Another", category="Api", is_executed=True)
    # Child listed before its parent: the tree puts it after.
    doc = build_report_document(_engagement(), _SECTIONS, [], [child, parent, other])
    rows = [(t.ref, t.number, t.title, t.parent_ref, t.status_label) for t in doc.testcases]
    assert rows == [
        ("T1", "1", "Another", None, "Executed"),
        ("T2", "2", "Parent", None, "Pass"),
        ("T3", "2.1", "Child", "T2", "Not Executed"),
    ]
    assert doc.testcase_summary == {"total": 3, "executed": 2, "passed": 1, "failed": 0}


def test_marks_inherit_clamp_and_roll_up_to_the_banner():
    f_default = _finding("Default")                                   # → engagement default C
    f_secret = _finding("Secret", classification_level="S")
    f_over = _finding("Over", classification_level="TS")              # clamped to ceiling S
    ev_inherit = _evidence()
    ev_own = _evidence(classification_level="U")
    f_default.evidence = [ev_inherit, ev_own, _evidence(include_in_report=False)]
    doc = build_report_document(_engagement(default="C", ceiling="S"), _SECTIONS,
                                [f_default, f_secret, f_over], [], marking_profile=_profile())
    marks = {f.title: f.mark.token for f in doc.findings}
    assert marks == {"Default": "(C)", "Secret": "(S)", "Over": "(S)"}
    ev = doc.finding(f_default.id).evidence
    assert [e.mark.token for e in ev] == ["(C)", "(U)"]                # excluded evidence dropped
    assert doc.banner.text == "SECRET" and doc.banner.bg == "#C8102E"
    # Unmarked structural headings carry the lowest level; aggregates the default.
    assert doc.structural_mark.token == "(U)" and doc.default_mark.token == "(C)"
    assert doc.sections[0].heading_mark.token == "(U)" and doc.sections[0].mark.token == "(C)"


def test_explicit_section_mark_wins_and_inherit_mode():
    sections = [_section(SectionType.TEXT, "Marked", level="S"), _section(SectionType.TEXT, "Plain")]
    doc = build_report_document(_engagement(default="C"), sections, [], [],
                                marking_profile=_profile(static_heading_marks="INHERIT"))
    assert [s.heading_mark.token for s in doc.sections] == ["(S)", "(C)"]
    assert doc.banner.level == "S"


def test_no_profile_means_no_marks():
    doc = build_report_document(_engagement(default="S"), _SECTIONS, [_finding("x")], [])
    assert doc.banner is None and not doc.findings[0].mark and doc.findings[0].mark.token == ""


def test_markdown_carries_banner_and_portion_marks():
    f = _finding("Secret thing", classification_level="S", technical_details="deep")
    md = MarkdownReportGenerator(_engagement(default="C"), _SECTIONS, [f], [_tc("T")],
                                 marking_profile=_profile()).generate()
    lines = md.strip().splitlines()
    assert lines[0] == "**SECRET**" and lines[-1] == "**SECRET**"
    assert "_Handle with care_" in md
    assert "## (U) Intro" in md and "### F01: (S) Secret thing" in md
    assert "#### Technical Details" in md
    assert "| (C) | 1 | T |" in md

    plain = MarkdownReportGenerator(_engagement(default="C"), _SECTIONS, [f], []).generate()
    assert "(S)" not in plain and "SECRET" not in plain and "## Intro" in plain


def test_formats_agree_on_ids_and_marks():
    crit = _finding("Crit", "CRITICAL", classification_level="S")
    low = _finding("Low", "LOW")
    parent = _tc("Parent")
    child = _tc("Child", parent_id=parent.id, findings=[low])
    args = (_engagement(default="C"), _SECTIONS, [low, crit], [child, parent], [])
    kw = dict(marking_profile=_profile())

    html = HTMLReportGenerator(*args, theme=None, storage=None, **kw).generate()
    data = _payload(html)
    assert [(f["id"], f["title"], f["mark"]) for f in data["findings"]] == [("F01", "Crit", "(S)"), ("F02", "Low", "(C)")]
    assert [(t["id"], t["label"], t["parent"], t["finds"]) for t in data["testcases"]] == [
        ("T1", "Parent", None, []), ("T2", "Child", "T1", ["F02"])]
    assert data["marking"]["banner"] == "SECRET"

    md = MarkdownReportGenerator(*args, **kw).generate()
    assert md.index("F01: (S) Crit") < md.index("F02: (C) Low")
    assert "F02 Low (Low)" in md

    pdf = PDFReportGenerator(*args, **kw)
    dF, dT = pdf._display_ids()
    assert dF == {crit.id: "F01", low.id: "F02"} and dT == {parent.id: "T1", child.id: "T2"}
    assert pdf._banner_level == "S"
