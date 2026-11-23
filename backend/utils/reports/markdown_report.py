"""Markdown report generator."""
import re
from datetime import datetime
from html import unescape as _html_unescape
from models.cleanup_artifact import CleanupArtifact
from models.engagement import Engagement
from models.finding import Finding
from models.report_layout import ReportSection
from models.report_theme import ReportTheme
from models.testcase import TestCase
from typing import List, Optional
from utils.reports.content import SEVERITY_ORDER, build_report_document
from utils.reports.common import _DEFAULTS


def _markdown_from_html(html: str) -> str:
    """Report field bodies to markdown. They are stored as markdown by the
    editor (tiptap-markdown, html:false: prose "<" is saved as "&lt;", code
    is saved verbatim); the HTML conversions handle any legacy HTML. Code
    spans and fences already in the source pass through untouched, so a
    literal "<file>" in code isn't taken for a tag."""
    if not html:
        return ""
    parts = _CODE_RE.split(html)
    return ''.join(p if i % 2 else _html_segment_to_markdown(p)
                   for i, p in enumerate(parts)).strip()


def _html_segment_to_markdown(text: str) -> str:
    text = re.sub(r'<h1[^>]*>(.*?)</h1>', r'# \1\n', text, flags=re.DOTALL)
    text = re.sub(r'<h2[^>]*>(.*?)</h2>', r'## \1\n', text, flags=re.DOTALL)
    text = re.sub(r'<h3[^>]*>(.*?)</h3>', r'### \1\n', text, flags=re.DOTALL)
    text = re.sub(r'<strong>(.*?)</strong>', r'**\1**', text, flags=re.DOTALL)
    text = re.sub(r'<b>(.*?)</b>', r'**\1**', text, flags=re.DOTALL)
    text = re.sub(r'<em>(.*?)</em>', r'*\1*', text, flags=re.DOTALL)
    text = re.sub(r'<i>(.*?)</i>', r'*\1*', text, flags=re.DOTALL)
    text = re.sub(r'<br\s*/?>', '\n', text)
    text = re.sub(r'<p[^>]*>(.*?)</p>', r'\1\n\n', text, flags=re.DOTALL)
    text = re.sub(r'<li[^>]*>(.*?)</li>', r'- \1\n', text, flags=re.DOTALL)
    text = re.sub(r'</?[uo]l[^>]*>', '', text)
    text = re.sub(r'<pre[^>]*><code[^>]*>(.*?)</code></pre>', r'```\n\1\n```\n', text, flags=re.DOTALL)
    text = re.sub(r'<code>(.*?)</code>', r'`\1`', text, flags=re.DOTALL)
    # Strip the remaining real tags while text is still entity-encoded, so
    # only markup goes: decoding first deleted any "<…>" the author wrote as
    # text (<username>, List<String>, code). Then decode, and write "<" as
    # "&lt;" outside code so decoded text such as "<img onerror=…>" can't act
    # as raw HTML in a markdown viewer. An entity is inert in every renderer
    # (a backslash escape isn't: Python-Markdown passes "\<tag>" through);
    # inside code spans and fences a literal "<" is already inert.
    text = re.sub(r'<[^>]+>', '', text)
    text = _html_unescape(text).replace('\xa0', ' ')
    return _escape_lt_outside_code(text)


_CODE_RE = re.compile(r'(```.*?```|`[^`\n]*`)', re.DOTALL)


def _escape_lt_outside_code(text: str) -> str:
    parts = _CODE_RE.split(text)
    return ''.join(p if i % 2 else p.replace('<', '&lt;') for i, p in enumerate(parts))


# ═══════════════════════════════════════════════════════════════════
# Markdown Report Generator
# ═══════════════════════════════════════════════════════════════════

def _md_cell(text) -> str:
    """A value safe inside a Markdown table cell."""
    return str(text or '').replace('\n', ' ').replace('|', '\\|')


class MarkdownReportGenerator:
    """Plain Markdown rendering of the report document: same content, order
    and portion marks as the PDF; the banner opens and closes the file."""

    def __init__(
        self,
        engagement: Engagement,
        sections: List[ReportSection],
        findings: List[Finding],
        testcases: List[TestCase],
        cleanup_artifacts: List[CleanupArtifact] = None,
        theme: Optional[ReportTheme] = None,
        finding_custom_fields=None,
        marking_profile=None,
    ):
        self.doc = build_report_document(
            engagement, sections, findings, testcases, cleanup_artifacts,
            theme=theme, marking_profile=marking_profile,
            finding_custom_fields=finding_custom_fields,
            default_title=_DEFAULTS['cover_title'])

    @staticmethod
    def _p(mark) -> str:
        return f'{mark.token} ' if mark.token else ''

    def _mark_column(self) -> bool:
        m = self.doc.marking
        return bool(m and m.inline_marks)

    def generate(self) -> str:
        doc = self.doc
        parts = []
        if doc.banner:
            parts.append(f'**{doc.banner.text}**\n')
        parts.append(f'# {doc.title}: {doc.engagement_name}\n')
        parts.append(f'**Client:** {doc.client}  ')
        parts.append(f'**Date:** {datetime.now().strftime("%B %d, %Y")}\n')
        parts.append('---\n')

        render = {
            'TEXT': self._render_text_section,
            'FINDINGS': self._render_findings_section,
            'TESTCASES': self._render_testcases_section,
            'CLEANUP_ARTIFACTS': self._render_cleanup_artifacts_section,
        }
        for section in doc.sections:
            if section.kind in render:
                parts.append(render[section.kind](section))

        if doc.banner:
            statement = doc.marking.distribution_statement if doc.marking else None
            if statement:
                parts.append(f'_{statement}_\n')
            parts.append(f'**{doc.banner.text}**\n')
        return '\n'.join(parts)

    def _heading(self, section) -> str:
        return f'## {self._p(section.heading_mark)}{section.title}\n\n'

    def _fields(self, fields, level='####') -> str:
        return ''.join(f'{level} {f.label}\n\n{_markdown_from_html(f.markdown)}\n\n' for f in fields)

    def _render_text_section(self, section) -> str:
        md = self._heading(section)
        content = _markdown_from_html(section.content) if section.content else ''
        if content:
            md += content + '\n'
        return md + '\n'

    def _render_findings_section(self, section) -> str:
        doc = self.doc
        md = self._heading(section)
        if not doc.findings:
            return md + 'No findings recorded.\n\n'

        sm = self._p(doc.structural_mark)
        md += f'### {sm}Severity Summary\n\n'
        md += '| Severity | Count |\n|----------|-------|\n'
        for sev in SEVERITY_ORDER:
            md += f'| {sev} | {doc.severity_counts.get(sev, 0)} |\n'
        md += '\n'

        for f in doc.findings:
            md += f'### {f.ref}: {self._p(f.mark)}{f.title}\n\n'
            md += f'- **Severity:** {f.severity}\n'
            md += f'- **Affected Asset(s):** {", ".join(a.name for a in f.assets) or "N/A"}\n'
            if f.score['text']:
                md += f'- **{f.score["label"]}:** {f.score["text"]}\n'
            for label, value in f.custom_fields:
                md += f'- **{label}:** {value}\n'
            md += '\n' + self._fields(f.fields)
            ev = [e for e in f.evidence]
            if ev:
                md += '#### Evidence\n\n'
                for e in ev:
                    cap = e.description or e.filename
                    md += f'- {self._p(e.mark)}{cap}' + (f' [{e.filename}]' if e.description and e.filename else '') + '\n'
                md += '\n'
            md += '---\n\n'
        return md

    def _render_testcases_section(self, section) -> str:
        doc = self.doc
        md = self._heading(section)
        if not doc.testcases:
            return md + 'No test cases recorded.\n\n'

        mcol = self._mark_column()
        s = doc.testcase_summary
        md += (f'{s["total"]} test case{"s" if s["total"] != 1 else ""} · {s["executed"]} executed · '
               f'{s["passed"]} passed · {s["failed"]} failed\n\n')
        md += ('| Mark ' if mcol else '') + '| # | Title | Category | Status |\n'
        md += ('|------' if mcol else '') + '|---|-------|----------|--------|\n'
        for t in doc.testcases:
            md += ((f'| {_md_cell(t.mark.token)} ' if mcol else '')
                   + f'| {t.number} | {_md_cell(t.title)} | {_md_cell(t.category)} | {t.status_label} |\n')
        md += '\n'

        for t in doc.testcases:
            md += f'### {t.number} {self._p(t.mark)}{t.title}\n\n'
            md += f'- **Status:** {t.status_label}\n'
            if t.category:
                md += f'- **Category:** {t.category}\n'
            if t.assets:
                md += f'- **Assets:** {", ".join(t.assets)}\n'
            if t.findings:
                found = ', '.join(f'{f.ref + " " if f.ref else ""}{f.title} ({f.severity.title()})' for f in t.findings)
                md += f'- **Discovered Findings:** {found}\n'
            md += '\n' + self._fields(t.fields)
        return md

    def _render_cleanup_artifacts_section(self, section) -> str:
        doc = self.doc
        md = self._heading(section)
        if not doc.cleanup:
            return md + 'No cleanup artifacts recorded.\n\n'

        mcol = self._mark_column()
        md += ('| Mark ' if mcol else '') + '| Title | Type | Status | Location |\n'
        md += ('|------' if mcol else '') + '|-------|------|--------|----------|\n'
        for ca in doc.cleanup:
            md += ((f'| {_md_cell(ca.mark.token)} ' if mcol else '')
                   + f'| {_md_cell(ca.title)} | {_md_cell(ca.artifact_type)} | {_md_cell(ca.status)} '
                   f'| {_md_cell(ca.location or "N/A")} |\n')
        md += '\n'

        for idx, ca in enumerate(doc.cleanup, 1):
            md += f'### {idx}. {self._p(ca.mark)}{ca.title}\n\n'
            md += f'- **Type:** {ca.artifact_type}\n'
            md += f'- **Status:** {ca.status}\n'
            if ca.location:
                md += f'- **Location:** {ca.location}\n'
            if ca.assets:
                md += f'- **Affected Asset(s):** {", ".join(ca.assets)}\n'
            if ca.finding_refs:
                md += f'- **Findings:** {", ".join(ca.finding_refs)}\n'
            md += '\n' + self._fields(ca.fields) + '---\n\n'
        return md
