"""PDF report generator: composes the per-section mixins and drives the build."""
import logging
import io
import re
from models.cleanup_artifact import CleanupArtifact
from models.engagement import Engagement
from models.finding import Finding
from models.report_layout import ReportSection
from models.report_theme import ReportTheme
from models.testcase import TestCase
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import PageBreak, Spacer
from typing import List, Optional
from utils.reports.content import Mark, build_report_document
from utils.reports.common import _DEFAULTS, _SEV_COLORS, _SEV_THEME_KEY, _t
from utils.reports.pdf.attack_graph import AttackGraphMixin
from utils.reports.pdf.cover import CoverMixin
from utils.reports.pdf.findings import FindingsMixin
from utils.reports.pdf.marking import MarkingMixin
from utils.reports.pdf.overview import OverviewMixin
from utils.reports.pdf.page import _OutlineDocTemplate, _get_page_size, _make_numbered_canvas
from utils.reports.pdf.sections import SectionsMixin
from utils.reports.pdf.styles import StylesMixin
from utils.reports.pdf.text import _md_to_flowables

_log = logging.getLogger(__name__)


class PDFReportGenerator(MarkingMixin, StylesMixin, CoverMixin, OverviewMixin, FindingsMixin, AttackGraphMixin, SectionsMixin):
    def __init__(
        self,
        engagement: Engagement,
        sections: List[ReportSection],
        findings: List[Finding],
        testcases: List[TestCase],
        cleanup_artifacts: List[CleanupArtifact] = None,
        theme: Optional[ReportTheme] = None,
        storage=None,
        markdown_image_map: Optional[dict] = None,
        marking_profile=None,
        finding_custom_fields=None,
        chain_edges=None,
        chain_vault_items=None,
    ):
        self.engagement = engagement
        self.theme = theme
        self.storage = storage
        # What the report says (order, ids, fields, marks, banner) — shared
        # with the Markdown and HTML renderers; this class only lays it out.
        self.doc = build_report_document(
            engagement, sections, findings, testcases, cleanup_artifacts,
            theme=theme, marking_profile=marking_profile,
            finding_custom_fields=finding_custom_fields,
            default_title=_DEFAULTS['cover_title'])
        # ORM rows in document order, for the attack-graph builders.
        self.findings = [f.src for f in self.doc.findings]
        self.testcases = [t.src for t in self.doc.testcases]
        self.cleanup_artifacts = [c.src for c in self.doc.cleanup]
        # Operator-authored attack-chain edges (ChainLink) + the vault items
        # they touch. Empty → the attack-path graphs fall back to the
        # association-derived subgraphs (byte-identical to pre-chain output).
        self.chain_edges = chain_edges or []
        self.chain_vault_items = chain_vault_items or {}
        # Portion marking — None when no profile is selected (marking disabled).
        self.marking = self.doc.marking
        # Document banner level (high-water mark of every portion).
        self._banner_level = self.doc.banner_level
        # { image_id: { storage_key, content_type } } — pre-loaded by the
        # route so this class needs no DB session. Used by _md_to_flowables
        # via _resolve_markdown_image to embed inline pasted/dropped images.
        self.markdown_image_map = markdown_image_map or {}
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    def _resolve_markdown_image(self, src: str) -> Optional[bytes]:
        """Resolve a markdown image URL to image bytes, or None.

        Accepts /api/markdown-images/<id>, /markdown-images/<id>, or just
        <id>; pulls the storage_key from the pre-loaded map and downloads
        from MinIO.
        """
        if not src or self.storage is None:
            return None
        m = re.search(r'/markdown-images/([^/?#]+)', src)
        image_id = m.group(1) if m else src
        # Drop any extension we tacked on the URL (the DB id is a UUID)
        image_id = image_id.rsplit('.', 1)[0]
        info = self.markdown_image_map.get(image_id)
        if not info:
            return None
        try:
            buf = io.BytesIO()
            self.storage.s3.download_fileobj(self.storage.bucket_name, info['storage_key'], buf)
            return buf.getvalue()
        except Exception as exc:
            _log.warning(f'Could not fetch markdown image {image_id!r}: {exc}')
            return None

    # ── Severity colors (themeable) ───────────────────────────────

    def _sev_hex(self, sev: str) -> str:
        key = _SEV_THEME_KEY.get((sev or '').upper())
        return (_t(self.theme, key) if key else None) or _SEV_COLORS.get((sev or '').upper(), '#64748B')

    def _md_flowables(self, text, style, mark: Mark, **kw):
        """Markdown → flowables, inline images marked with the portion's mark."""
        return _md_to_flowables(
            text, style, image_resolver=self._resolve_markdown_image,
            mark_text=mark.token or None,
            mark_anchors=self.marking.image_anchors if self.marking else None,
            mark_fg=mark.color, **kw)

    # ── Generate ──────────────────────────────────────────────────

    def generate(self) -> bytes:
        buffer   = io.BytesIO()
        page_size = _get_page_size(_t(self.theme, 'page_size'))
        doc = _OutlineDocTemplate(
            buffer, pagesize=page_size,
            rightMargin=54, leftMargin=54,
            topMargin=60, bottomMargin=52,
        )
        elements = []

        show_cover = _t(self.theme, 'show_cover_page')

        if show_cover:
            # Cover page placeholder — actual drawing happens in onFirstPage callback
            elements.append(Spacer(1, 0.1))
            elements.append(PageBreak())

        # Table of contents
        self._render_toc(elements)

        # Risk-overview dashboard (charts) — mirrors the interactive report
        if _t(self.theme, 'show_risk_overview') is not False:
            self._render_overview(elements)

        # Full-engagement attack graph (when small enough to read on a static page)
        if _t(self.theme, 'show_attack_graph') is not False:
            self._render_attack_graph_section(elements)

        # Sections
        render = {
            'TEXT': self._render_text_section,
            'FINDINGS': self._render_findings_section,
            'TESTCASES': self._render_testcases_section,
            'CLEANUP_ARTIFACTS': self._render_cleanup_artifacts_section,
        }
        for section in self.doc.sections:
            if section.page_break_before:
                elements.append(PageBreak())
            if section.kind in render:
                render[section.kind](elements, section)

        # Choose which first-page callback to use
        if show_cover:
            first_page_cb = self._cover_and_header
        else:
            first_page_cb = self._header_footer

        # "Page X of Y" needs the total page count, which only a counting canvas
        # knows. Use it when both page numbers and the X-of-Y option are on; the
        # header/footer callback then skips drawing the plain "Page X".
        build_kwargs = dict(onFirstPage=first_page_cb, onLaterPages=self._header_footer)
        if _t(self.theme, 'show_page_numbers') and _t(self.theme, 'show_page_x_of_y'):
            build_kwargs['canvasmaker'] = _make_numbered_canvas(
                _t(self.theme, 'font_family'),
                _t(self.theme, 'muted_text_color'),
                skip_first=bool(show_cover),
            )

        # multiBuild resolves the TableOfContents page numbers over repeated passes.
        doc.multiBuild(elements, **build_kwargs)
        pdf_value = buffer.getvalue()
        buffer.close()
        return pdf_value

    def _cover_and_header(self, canvas, doc):
        """On the very first page, draw the cover; rely on platypus for the rest."""
        canvas.saveState()
        self._draw_cover(canvas, doc)
        canvas.restoreState()
        # Banner is painted on the cover too (top/bottom or TLP chip).
        self._draw_banner(canvas, doc)

    # ── Section renderers ─────────────────────────────────────────

    def _render_text_section(self, elements, section):
        elements.append(self._section_header_table(section.title.upper(), section))
        elements.append(Spacer(1, 14))
        if section.content:
            elements.extend(self._md_flowables(section.content, self.styles['BodyText2'], section.mark))
        elements.append(Spacer(1, 20))
