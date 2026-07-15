"""utils/report_generator.py coverage — HTML-output XSS escaping first.

A stored-XSS class was flagged for the HTML report deliverable: finding
titles / descriptions / evidence captions are author-controlled markdown and
must never reach the rendered HTML as live markup. These tests pin the
escaping/sanitisation contract on the security-critical surfaces:

  - ``_escape_xml``           — the low-level element/attribute escaper
  - ``HTMLReportGenerator._md`` — markdown fields: raw HTML escaped, and
                                  javascript:/vbscript:/data: link schemes
                                  neutralised
  - ``HTMLReportGenerator.generate`` — end-to-end: a malicious finding
                                  title + description cannot inject a live
                                  ``<script>`` / event handler into the doc
  - ``_markdown_from_html``    — entity-encoded markup can't survive the
                                  Markdown-export sanitisation

Plus the pure formatting/section-assembly helpers (``_v``, custom-field
rows, portion-mark prefixes). We do NOT render a real PDF — only the
string-producing HTML/markdown paths and pure helpers are exercised.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from models.report_layout import SectionType

import utils.report_generator as rg
from utils.report_generator import (
    _escape_xml,
    _v,
    _format_report_cf_value,
    _report_cf_rows,
    _markdown_from_html,
    HTMLReportGenerator,
    MarkdownReportGenerator,
)


# ─────────────────────────────────────────────────────────────────────
# Fakes — the generators only read attributes, so SimpleNamespace suffices.
# ─────────────────────────────────────────────────────────────────────

def _asset(name="host01"):
    return SimpleNamespace(name=name)


def _finding(**over):
    base = dict(
        title="Benign Finding",
        severity="HIGH",
        assets=[_asset()],
        cvss_score=None,
        cvss_vector=None,
        description="",
        impact="",
        steps_to_reproduce="",
        mitigations="",
        references="",
        custom_fields={},
        evidence=[],
        classification_level=None,
        classification_suffix=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


def _section(section_type=SectionType.FINDINGS, title="Findings", content=""):
    return SimpleNamespace(
        section_type=section_type,
        title=title,
        content=content,
        classification_level=None,
        classification_suffix=None,
    )


def _engagement(name="Op Nightfall", client_name="ACME"):
    return SimpleNamespace(
        name=name,
        client_name=client_name,
        default_classification_level=None,
    )


def _html_gen(findings=None, sections=None, testcases=None, cleanup=None, engagement=None):
    return HTMLReportGenerator(
        engagement=engagement or _engagement(),
        sections=sections if sections is not None else [_section()],
        findings=findings or [],
        testcases=testcases or [],
        cleanup_artifacts=cleanup or [],
        theme=None,
        storage=None,
        marking_profile=None,
    )


# ═══════════════════════════════════════════════════════════════════
# _escape_xml — the escaping primitive
# ═══════════════════════════════════════════════════════════════════


def test_escape_xml_escapes_all_five_metacharacters():
    assert _escape_xml('<a href="x">& \'') == "&lt;a href=&quot;x&quot;&gt;&amp; &#39;"


def test_escape_xml_ampersand_first_no_double_escape():
    # & must be replaced before < / > so we don't produce &amp;lt;.
    assert _escape_xml("<") == "&lt;"
    assert _escape_xml("&lt;") == "&amp;lt;"


def test_escape_xml_none_and_non_str():
    assert _escape_xml(None) == ""
    assert _escape_xml(123) == "123"


def test_escape_xml_neutralises_script_tag():
    out = _escape_xml("<script>alert(1)</script>")
    assert "<script>" not in out
    assert out == "&lt;script&gt;alert(1)&lt;/script&gt;"


# ═══════════════════════════════════════════════════════════════════
# _v / custom-field formatting helpers
# ═══════════════════════════════════════════════════════════════════


def test_v_handles_none_enum_and_str():
    assert _v(None) == "N/A"
    assert _v(SimpleNamespace(value="CRITICAL")) == "CRITICAL"
    assert _v("plain") == "plain"


def test_format_report_cf_value_variants():
    assert _format_report_cf_value("boolean", True) == "Yes"
    assert _format_report_cf_value("boolean", False) == "No"
    assert _format_report_cf_value("multiselect", ["a", "b"]) == "a, b"
    assert _format_report_cf_value("text", "hi") == "hi"
    # Empty-ish values collapse to None so they're skipped in the report.
    assert _format_report_cf_value("text", None) is None
    assert _format_report_cf_value("text", "") is None
    assert _format_report_cf_value("multiselect", []) is None


def test_report_cf_rows_filters_empty_and_reads_defs():
    defs = [
        SimpleNamespace(field_type="text", field_key="k1", label="Owner"),
        SimpleNamespace(field_type="text", field_key="k2", label="Empty"),
    ]
    rows = _report_cf_rows(defs, {"k1": "alice", "k2": ""})
    assert rows == [("Owner", "alice")]


def test_report_cf_rows_none_inputs():
    assert _report_cf_rows(None, None) == []


# ═══════════════════════════════════════════════════════════════════
# HTMLReportGenerator._md — markdown field sanitisation (XSS-critical)
# ═══════════════════════════════════════════════════════════════════


def test_md_escapes_raw_script_tag():
    gen = _html_gen()
    out = gen._md("Intro <script>alert(document.cookie)</script> tail")
    assert "<script>" not in out
    assert "alert(document.cookie)" in out          # text preserved, inert
    assert "&lt;script&gt;" in out


def test_md_escapes_img_onerror_handler():
    gen = _html_gen()
    out = gen._md('<img src=x onerror="alert(1)">')
    # The <img> must not survive as a live tag.
    assert "<img" not in out.lower().replace("&lt;img", "")
    assert "&lt;img" in out


def test_md_neutralises_javascript_link_scheme():
    gen = _html_gen()
    out = gen._md("[click me](javascript:alert(1))")
    # No href/src attribute may carry a javascript: scheme.
    assert re.search(r'(?i)(href|src)\s*=\s*"\s*javascript:', out) is None


@pytest.mark.parametrize("scheme", ["javascript", "vbscript", "data"])
def test_md_neutralises_dangerous_schemes_generic(scheme):
    gen = _html_gen()
    out = gen._md(f"[x]({scheme}:whatever)")
    assert re.search(rf'(?i)(href|src)\s*=\s*"\s*{scheme}:', out) is None


def test_md_empty_returns_empty():
    assert _html_gen()._md("") == ""
    assert _html_gen()._md(None) == ""


# ═══════════════════════════════════════════════════════════════════
# HTMLReportGenerator.generate — end-to-end stored-XSS pin
# ═══════════════════════════════════════════════════════════════════


def test_generate_escapes_malicious_finding_title_and_description():
    f = _finding(
        title="<script>steal()</script>Injected",
        description="Payload: <img src=x onerror=alert(1)>",
    )
    gen = _html_gen(findings=[f], sections=[_section(SectionType.FINDINGS)])
    html = gen.generate()
    # The document is produced and the live markup is gone.
    assert "<!DOCTYPE html>" in html
    assert "<script>steal()</script>" not in html
    assert "&lt;script&gt;" in html
    # The <img> is neutralised: escaped to inert text, never a live tag.
    assert "<img" not in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html


def test_generate_escapes_engagement_name_in_title_and_cover():
    eng = _engagement(name='Op "><script>x</script>', client_name="<b>C</b>")
    gen = _html_gen(findings=[], sections=[], engagement=eng)
    html = gen.generate()
    assert "<script>x</script>" not in html
    assert "<b>C</b>" not in html
    assert "&lt;b&gt;C&lt;/b&gt;" in html


def test_generate_renders_benign_finding_fields():
    f = _finding(
        title="SQL Injection",
        severity="CRITICAL",
        cvss_score=9.1,
        assets=[_asset("db01"), _asset("db02")],
        description="Injectable parameter.",
    )
    gen = _html_gen(findings=[f], sections=[_section(SectionType.FINDINGS)])
    html = gen.generate()
    assert "SQL Injection" in html
    assert "CRITICAL" in html
    assert "db01, db02" in html
    assert "9.1" in html
    # Severity distribution table present.
    assert "Severity Distribution" in html


def test_generate_escapes_cvss_vector():
    f = _finding(cvss_score=7.5, cvss_vector='"><script>y</script>')
    gen = _html_gen(findings=[f], sections=[_section(SectionType.FINDINGS)])
    html = gen.generate()
    assert "<script>y</script>" not in html


def test_findings_html_empty_state():
    gen = _html_gen(findings=[], sections=[_section(SectionType.FINDINGS)])
    assert "No findings recorded" in gen._findings_html()


# ── testcases / cleanup section escaping ─────────────────────────────


def test_testcases_html_escapes_title():
    tc = SimpleNamespace(
        title="<script>tc</script>",
        category="injection",
        is_executed=True,
        is_successful=True,
        classification_level=None,
        classification_suffix=None,
    )
    gen = _html_gen(testcases=[tc])
    out = gen._testcases_html()
    assert "<script>tc</script>" not in out
    assert "&lt;script&gt;" in out
    assert "✓ Pass" in out


def test_cleanup_html_escapes_title_and_location():
    ca = SimpleNamespace(
        title="<script>ca</script>",
        artifact_type="backdoor",
        status="removed",
        location='<img src=x onerror=1>',
        classification_level=None,
        classification_suffix=None,
    )
    gen = _html_gen(cleanup=[ca])
    out = gen._cleanup_html()
    assert "<script>ca</script>" not in out
    assert "<img src=x" not in out
    assert "&lt;script&gt;" in out


def test_section_bar_escapes_title():
    gen = _html_gen()
    bar = gen._section_bar(_section(title="<b>Overview</b>"))
    assert "<b>Overview</b>" not in bar
    # Titles are upper-cased then escaped.
    assert "&lt;B&gt;OVERVIEW&lt;/B&gt;" in bar


# ═══════════════════════════════════════════════════════════════════
# _markdown_from_html — Markdown export sanitisation
# ═══════════════════════════════════════════════════════════════════


def test_markdown_from_html_converts_basic_tags():
    assert _markdown_from_html("<strong>bold</strong>") == "**bold**"
    assert _markdown_from_html("<h1>Title</h1>").startswith("# Title")
    assert "*em*" in _markdown_from_html("<em>em</em>")


def test_markdown_from_html_strips_entity_encoded_markup():
    # The comment in-source: entity-encoded markup must not survive the
    # unescape-then-strip pass (defends against &lt;img onerror=…&gt;).
    out = _markdown_from_html("safe &lt;img src=x onerror=alert(1)&gt; text")
    assert "<img" not in out
    assert "onerror" not in out
    assert "safe" in out and "text" in out


def test_markdown_from_html_strips_raw_tags():
    out = _markdown_from_html("<script>evil()</script>hello")
    assert "<script>" not in out
    assert "hello" in out


def test_markdown_from_html_empty():
    assert _markdown_from_html("") == ""
    assert _markdown_from_html(None) == ""


# ═══════════════════════════════════════════════════════════════════
# MarkdownReportGenerator — assembly + severity sort
# ═══════════════════════════════════════════════════════════════════


def test_markdown_generator_sorts_findings_by_severity_desc():
    low = _finding(title="Low one", severity="LOW")
    crit = _finding(title="Crit one", severity="CRITICAL")
    gen = MarkdownReportGenerator(
        engagement=_engagement(),
        sections=[_section(SectionType.FINDINGS, title="Findings")],
        findings=[low, crit],
        testcases=[],
    )
    md = gen.generate()
    # Critical finding heading appears before the low one.
    assert md.index("Finding 1: Crit one") < md.index("Finding 2: Low one")
    assert "**Client:** ACME" in md


def test_markdown_generator_findings_sanitises_html_in_description():
    f = _finding(title="Bug", severity="HIGH",
                 description="<script>x</script> body")
    gen = MarkdownReportGenerator(
        engagement=_engagement(),
        sections=[_section(SectionType.FINDINGS, title="Findings")],
        findings=[f],
        testcases=[],
    )
    md = gen.generate()
    assert "<script>" not in md
    assert "body" in md
