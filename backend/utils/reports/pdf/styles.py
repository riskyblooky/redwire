"""PDF report — paragraph styles derived from the report theme."""
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from utils.reports.common import _t
from utils.reports.pdf.text import _bold_font


class StylesMixin:
    """Paragraph styles derived from the report theme."""

    # ── Styles ────────────────────────────────────────────────────

    def _setup_custom_styles(self):
        font       = _t(self.theme, 'font_family')
        font_bold  = _bold_font(font)
        heading_c  = _t(self.theme, 'header_text_color')
        body_c     = _t(self.theme, 'body_text_color')
        muted_c    = _t(self.theme, 'muted_text_color')
        body_size  = _t(self.theme, 'font_size_body')
        h_size     = _t(self.theme, 'font_size_heading')

        add = self.styles.add

        add(ParagraphStyle(
            name='ReportTitle',
            parent=self.styles['Heading1'],
            fontSize=32, spaceAfter=14, spaceBefore=0,
            fontName=font_bold,
            textColor=colors.white,
            alignment=1, leading=38,
        ))
        add(ParagraphStyle(
            name='CoverSubtitle',
            parent=self.styles['Normal'],
            fontSize=14, spaceAfter=6,
            fontName=font_bold,
            textColor=colors.HexColor('#94A3B8'),
            alignment=1,
        ))
        add(ParagraphStyle(
            name='CoverMeta',
            parent=self.styles['Normal'],
            fontSize=10, spaceAfter=4,
            fontName=font,
            textColor=colors.HexColor('#CBD5E1'),
            alignment=1,
        ))
        add(ParagraphStyle(
            name='CoverClassification',
            parent=self.styles['Normal'],
            fontSize=9, spaceAfter=0,
            fontName=font_bold,
            textColor=colors.HexColor('#DC2626'),
            alignment=1,
            letterSpacing=2,
        ))
        add(ParagraphStyle(
            name='SectionTitle',
            parent=self.styles['Heading1'],
            fontSize=h_size, spaceBefore=6, spaceAfter=12,
            fontName=font_bold,
            textColor=colors.white,
            leading=h_size + 6,
        ))
        add(ParagraphStyle(
            name='SubSectionTitle',
            parent=self.styles['Heading2'],
            fontSize=13, spaceBefore=18, spaceAfter=8,
            fontName=font_bold,
            textColor=colors.HexColor(heading_c),
            leading=18,
        ))
        add(ParagraphStyle(
            name='FindingTitle',
            parent=self.styles['Heading2'],
            fontSize=12, spaceBefore=0, spaceAfter=4,
            fontName=font_bold,
            textColor=colors.white,
            leading=16,
        ))
        add(ParagraphStyle(
            name='Label',
            parent=self.styles['Normal'],
            fontSize=body_size - 1,
            fontName=font_bold,
            textColor=colors.HexColor(muted_c),
            spaceAfter=2,
        ))
        add(ParagraphStyle(
            name='BodyText2',
            parent=self.styles['Normal'],
            fontSize=body_size,
            leading=body_size + 5,
            spaceAfter=6,
            fontName=font,
            textColor=colors.HexColor(body_c),
        ))
        add(ParagraphStyle(
            name='Caption',
            parent=self.styles['Normal'],
            fontSize=8, fontName=font,
            textColor=colors.HexColor(muted_c),
            alignment=1,
        ))
        add(ParagraphStyle(
            name='TOCEntry',
            parent=self.styles['Normal'],
            fontSize=body_size, fontName=font,
            textColor=colors.HexColor(body_c),
            spaceAfter=6,
            leftIndent=0,
        ))
        add(ParagraphStyle(
            name='Small',
            parent=self.styles['Normal'],
            fontSize=8, fontName=font,
            textColor=colors.HexColor(muted_c),
        ))
