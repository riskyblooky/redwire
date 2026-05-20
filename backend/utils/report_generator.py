import io
import logging
import base64
import math

_log = logging.getLogger(__name__)
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image, HRFlowable, KeepTogether
from reportlab.lib.units import inch, cm
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab import rl_config

# Defence-in-depth: this module never asks ReportLab to fetch a URL — every
# Image() flowable is built from a BytesIO we filled ourselves (MinIO download
# or markdown-image resolver). Locking trustedSchemes/trustedHosts down means
# that even if a future change lets unescaped user text reach Paragraph(), an
# `<img src="http://…">` / `file://…` in that text cannot make the report
# builder open a network connection or read a local file.
rl_config.trustedSchemes = []
rl_config.trustedHosts = []

from datetime import datetime
from models.engagement import Engagement
from models.finding import Finding, Severity
from models.testcase import TestCase
from models.cleanup_artifact import CleanupArtifact
from models.report_layout import ReportSection, SectionType
from models.report_theme import ReportTheme
from typing import List, Optional
import re


# ═══════════════════════════════════════════════════════════════════
# Palette — Dark Executive Red Team
# ═══════════════════════════════════════════════════════════════════

_DEFAULTS = {
    # Brand
    "primary_color":       "#DC2626",   # Red-600: Red Team accent
    "secondary_color":     "#1E293B",   # Slate-800: Dark section bars
    "cover_bg_color":      "#0F172A",   # Slate-900: Cover background
    "accent_line_color":   "#DC2626",   # Thin rule lines

    # Text
    "header_text_color":   "#0F172A",   # Near-black headings
    "body_text_color":     "#334155",   # Slate-700 body
    "muted_text_color":    "#64748B",   # Slate-500 labels/captions

    # Tables
    "table_header_bg":     "#1E293B",
    "table_header_text":   "#FFFFFF",
    "table_alt_row_bg":    "#F8FAFC",   # Slate-50 alternating rows

    # Typography
    "font_family":         "Helvetica",
    "font_size_body":      10,
    "font_size_heading":   16,

    # Layout
    "show_page_numbers":   True,
    "show_cover_page":     True,
    "cover_title":         "Red Team Assessment Report",
    "header_text":         None,
    "footer_text":         "CONFIDENTIAL",
    "page_size":           "letter",
}

# Severity colours
_SEV_COLORS = {
    "CRITICAL": "#DC2626",
    "HIGH":     "#EA580C",
    "MEDIUM":   "#D97706",
    "LOW":      "#2563EB",
    "INFO":     "#64748B",
}

_SEV_BG_COLORS = {
    "CRITICAL": "#FEF2F2",
    "HIGH":     "#FFF7ED",
    "MEDIUM":   "#FFFBEB",
    "LOW":      "#EFF6FF",
    "INFO":     "#F8FAFC",
}

_SEVERITY_RANK = {
    'CRITICAL': 5,
    'HIGH': 4,
    'MEDIUM': 3,
    'LOW': 2,
    'INFO': 1,
}


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

def _t(theme: Optional[ReportTheme], key: str):
    if theme:
        val = getattr(theme, key, None)
        if val is not None:
            return val
    return _DEFAULTS.get(key)


def _hex(theme: Optional[ReportTheme], key: str) -> colors.Color:
    return colors.HexColor(_t(theme, key))


def _severity_rank(severity) -> int:
    key = _v(severity).upper()
    return _SEVERITY_RANK.get(key, 0)


def _v(val) -> str:
    if val is None:
        return 'N/A'
    return val.value if hasattr(val, 'value') else str(val)


# ── Markdown → ReportLab inline / block conversion ────────────────────
#
# The frontend's MarkdownEditor stores fields (finding description, impact,
# steps_to_reproduce, mitigations, references, text-section content,
# cleanup description / notes) as raw markdown. The PDF generator used to
# strip HTML tags from those fields, which is a no-op for markdown — so
# `**bold**` and `# heading` rendered literally in the PDF.
#
# `_md_inline_to_rl` converts inline markdown (bold/italic/code/link) into
# the limited HTML subset that ReportLab's Paragraph supports.
# `_md_to_flowables` walks block-level markdown (headings, lists, code
# fences, blockquotes, paragraphs) and returns a list of flowables that
# can be dropped into a Paragraph stack or a Table cell.
#
# Inputs are escaped first so a stray `<` in user content doesn't break
# the Paragraph parser.

def _escape_xml(text: str) -> str:
    """Make `text` safe for ReportLab's Paragraph mini-markup, in both
    element-content and attribute-value position. `"` and `'` matter because
    several callers place the escaped string inside a double-quoted attribute
    (e.g. the markdown link → `<link href="…">` substitution below)."""
    if text is None:
        return ""
    return (
        str(text)
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;')
            .replace("'", '&#39;')
    )


def _md_inline_to_rl(text: str) -> str:
    """Convert inline markdown / TipTap HTML to ReportLab Paragraph-flavoured HTML.

    Markdown: **bold**, __bold__, *italic*, _italic_, `code`, [text](url),
    ~sub~ (subscript via tildes), ^sup^ (superscript via carets).

    Raw HTML pass-through (TipTap emits these for features that don't have
    pure markdown equivalents): <u>, <mark>, <sub>, <sup>,
    <span style="color:..."> / background-color, <br>.

    Strategy: pull out and stash the supported HTML tags before XML-escape,
    then re-insert at the end.
    """
    if not text:
        return ""

    # Step 1 — extract supported HTML constructs to placeholders so they
    # survive the XML-escape pass without becoming `&lt;u&gt;`.
    placeholders: list[str] = []

    def _stash(replacement: str) -> str:
        placeholders.append(replacement)
        return f'\x00P{len(placeholders) - 1}\x00'

    s = text

    # Underline
    s = re.sub(r'<u(?:\s[^>]*)?>(.*?)</u>', lambda m: _stash(f'<u>{_escape_xml(m.group(1))}</u>'), s, flags=re.DOTALL | re.IGNORECASE)
    # Highlight (mark)
    def _mark_repl(m):
        inner = _escape_xml(m.group(1))
        # Try to extract data-color or style="background-color: ..."
        bg = None
        attrs = m.group(0)[:m.group(0).index('>')]
        m_color = re.search(r'(?:data-color|background-color)\s*[:=]\s*[\'"]?(#?[0-9a-fA-F]{3,8})', attrs)
        if m_color:
            bg = m_color.group(1)
            if not bg.startswith('#') and len(bg) in (3, 6) and re.fullmatch(r'[0-9A-Fa-f]+', bg):
                bg = '#' + bg
        if bg:
            return _stash(f'<font backColor="{bg}">{inner}</font>')
        return _stash(f'<font backColor="#FDE68A">{inner}</font>')
    s = re.sub(r'<mark(?:\s[^>]*)?>(.*?)</mark>', _mark_repl, s, flags=re.DOTALL | re.IGNORECASE)
    # Subscript / superscript
    s = re.sub(r'<sub(?:\s[^>]*)?>(.*?)</sub>', lambda m: _stash(f'<sub>{_escape_xml(m.group(1))}</sub>'), s, flags=re.DOTALL | re.IGNORECASE)
    s = re.sub(r'<sup(?:\s[^>]*)?>(.*?)</sup>', lambda m: _stash(f'<sup>{_escape_xml(m.group(1))}</sup>'), s, flags=re.DOTALL | re.IGNORECASE)
    # Coloured span — color and/or background-color from inline style
    def _span_repl(m):
        attrs = m.group(1) or ''
        inner = _escape_xml(m.group(2))
        color = None
        bg = None
        m_c = re.search(r'(?<!-)color\s*:\s*(#?[0-9a-fA-F]{3,8})', attrs)
        if m_c:
            color = m_c.group(1)
            if not color.startswith('#') and re.fullmatch(r'[0-9A-Fa-f]+', color):
                color = '#' + color
        m_bg = re.search(r'background-color\s*:\s*(#?[0-9a-fA-F]{3,8})', attrs)
        if m_bg:
            bg = m_bg.group(1)
            if not bg.startswith('#') and re.fullmatch(r'[0-9A-Fa-f]+', bg):
                bg = '#' + bg
        font_attrs = ''
        if color:
            font_attrs += f' color="{color}"'
        if bg:
            font_attrs += f' backColor="{bg}"'
        if font_attrs:
            return _stash(f'<font{font_attrs}>{inner}</font>')
        return _stash(inner)
    s = re.sub(r'<span([^>]*)>(.*?)</span>', _span_repl, s, flags=re.DOTALL | re.IGNORECASE)
    # Hard line breaks
    s = re.sub(r'<br\s*/?>', lambda _: _stash('<br/>'), s, flags=re.IGNORECASE)

    # Step 2 — escape everything else
    s = _escape_xml(s)

    # Step 3 — markdown inline conversions
    # Inline code first (so its contents aren't re-processed)
    s = re.sub(r'`([^`]+)`', lambda m: f'<font name="Courier">{m.group(1)}</font>', s)
    # Bold
    s = re.sub(r'\*\*([^*]+?)\*\*', r'<b>\1</b>', s)
    s = re.sub(r'__([^_]+?)__', r'<b>\1</b>', s)
    # Italic (single * or _) — avoid eating bold markers we already replaced
    s = re.sub(r'(?<!\*)\*([^*\n]+?)\*(?!\*)', r'<i>\1</i>', s)
    s = re.sub(r'(?<!_)_([^_\n]+?)_(?!_)', r'<i>\1</i>', s)
    # Subscript ~text~ / superscript ^text^ (markdown shorthands)
    s = re.sub(r'~([^~\n]+?)~', r'<sub>\1</sub>', s)
    s = re.sub(r'\^([^\^\n]+?)\^', r'<sup>\1</sup>', s)
    # Links [text](url)
    s = re.sub(
        r'\[([^\]]+)\]\((https?://[^)\s]+)\)',
        r'<link href="\2" color="#2563EB">\1</link>',
        s,
    )

    # Step 4 — restore stashed HTML
    def _restore(m):
        idx = int(m.group(1))
        return placeholders[idx] if 0 <= idx < len(placeholders) else ''
    s = re.sub(r'\x00P(\d+)\x00', _restore, s)
    return s


def _md_to_flowables(
    text: str,
    body_style: ParagraphStyle,
    *,
    code_style: Optional[ParagraphStyle] = None,
    heading_style: Optional[ParagraphStyle] = None,
    bullet_style: Optional[ParagraphStyle] = None,
    max_chars: Optional[int] = None,
    image_resolver=None,
    max_image_width: float = 6.0 * inch,
    max_image_height: float = 4.0 * inch,
) -> list:
    """Convert markdown text into a list of ReportLab flowables.

    Block-level: headings (#/##/###), bullet/numbered lists, fenced code
    blocks (```), blockquotes (>), and paragraphs separated by blank lines.
    Inline: see `_md_inline_to_rl`.

    `max_chars` truncates the *input* (the cell body limit the old code
    enforced) before parsing, to keep huge fields from blowing out a
    table cell.
    """
    if not text:
        return []

    raw = text
    if max_chars is not None and len(raw) > max_chars:
        raw = raw[:max_chars] + '…'

    code_st = code_style or ParagraphStyle(
        name='_md_code', parent=body_style,
        fontName='Courier',
        fontSize=max(7, int(getattr(body_style, 'fontSize', 9)) - 1),
        backColor=colors.HexColor('#F1F5F9'),
        textColor=colors.HexColor('#0F172A'),
        borderPadding=4, leftIndent=6, rightIndent=6,
        spaceBefore=2, spaceAfter=4,
    )
    h_st = heading_style or ParagraphStyle(
        name='_md_h', parent=body_style,
        fontName=(getattr(body_style, 'fontName', 'Helvetica') + '-Bold')
            if not getattr(body_style, 'fontName', '').endswith('-Bold')
            else getattr(body_style, 'fontName', 'Helvetica-Bold'),
        fontSize=int(getattr(body_style, 'fontSize', 9)) + 2,
        spaceBefore=4, spaceAfter=2,
    )
    bullet_st = bullet_style or ParagraphStyle(
        name='_md_bullet', parent=body_style,
        leftIndent=14, bulletIndent=2, spaceAfter=1,
    )

    flowables: list = []
    lines = raw.split('\n')
    i = 0
    paragraph_buf: list[str] = []

    _ALIGN_MAP = {'left': 0, 'center': 1, 'right': 2, 'justify': 4}

    def _para_with_alignment(text_html: str) -> Paragraph:
        """If TipTap wrapped content in <p|div style='text-align:X'>, strip
        the wrapper and emit a Paragraph with the matching alignment."""
        m = re.match(
            r'^\s*<(p|div|h[1-6])([^>]*?)>\s*(.*?)\s*</\1>\s*$',
            text_html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if m:
            attrs = m.group(2) or ''
            inner = m.group(3)
            m_a = re.search(r'text-align\s*:\s*(left|center|right|justify)', attrs, flags=re.IGNORECASE)
            if m_a:
                align = _ALIGN_MAP[m_a.group(1).lower()]
                aligned_style = ParagraphStyle(
                    name='_md_aligned', parent=body_style, alignment=align,
                )
                return Paragraph(_md_inline_to_rl(inner), aligned_style)
            # Wrapper without alignment — just unwrap
            return Paragraph(_md_inline_to_rl(inner), body_style)
        return Paragraph(_md_inline_to_rl(text_html), body_style)

    def flush_paragraph():
        if paragraph_buf:
            joined = ' '.join(paragraph_buf).strip()
            if joined:
                flowables.append(_para_with_alignment(joined))
            paragraph_buf.clear()

    def _is_table_separator(s: str) -> bool:
        # GFM separator row: | --- | :---: | ---: |
        s = s.strip()
        if not s.startswith('|') or not s.endswith('|'):
            return False
        inner = s.strip('|')
        return all(re.fullmatch(r'\s*:?-{2,}:?\s*', c) for c in inner.split('|') if c.strip() != '')

    def _split_pipe_row(s: str) -> list[str]:
        s = s.strip()
        if s.startswith('|'):
            s = s[1:]
        if s.endswith('|'):
            s = s[:-1]
        return [c.strip() for c in s.split('|')]

    def _build_image_flowable(src: str) -> Optional[object]:
        """If image_resolver returns bytes, build a sized ReportLab Image flowable."""
        if not image_resolver:
            return None
        try:
            data = image_resolver(src)
        except Exception as exc:
            _log.warning(f'Image resolver failed for {src!r}: {exc}')
            return None
        if not data:
            return None
        try:
            buf = io.BytesIO(data)
            img = Image(buf)
            iw, ih = img.imageWidth, img.imageHeight
            if iw <= 0 or ih <= 0:
                return None
            ratio = min(max_image_width / iw, max_image_height / ih, 1.0)
            img.drawWidth = iw * ratio
            img.drawHeight = ih * ratio
            return img
        except Exception as exc:
            _log.warning(f'Failed to render markdown image {src!r}: {exc}')
            return None

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Standalone image — `![alt](url)` on its own line, or <img src=...>
        m_img = (
            re.match(r'^\s*!\[[^\]]*\]\(([^)\s]+)(?:\s+"[^"]*")?\)\s*$', line)
            or re.match(r'^\s*<img\b[^>]*?\bsrc=[\'"]([^\'"]+)[\'"][^>]*/?>\s*$', line, flags=re.IGNORECASE)
        )
        if m_img:
            flush_paragraph()
            src = m_img.group(1)
            img_flowable = _build_image_flowable(src)
            if img_flowable is not None:
                flowables.append(img_flowable)
                flowables.append(Spacer(1, 4))
            else:
                # Couldn't resolve — render the alt text or URL as plain text
                placeholder = re.sub(r'^\s*!\[([^\]]*)\].*$', r'[Image: \1]', line) if line.lstrip().startswith('!') else f'[Image: {src}]'
                flowables.append(Paragraph(_md_inline_to_rl(placeholder.strip()), body_style))
            i += 1
            continue

        # Markdown pipe table
        if (
            stripped.startswith('|')
            and i + 1 < len(lines)
            and _is_table_separator(lines[i + 1])
        ):
            flush_paragraph()
            header = _split_pipe_row(lines[i])
            i += 2  # skip header + separator
            body_rows: list[list[str]] = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                body_rows.append(_split_pipe_row(lines[i]))
                i += 1
            # Build ReportLab Table
            cell_style = ParagraphStyle(
                name='_md_tbl_cell', parent=body_style,
                fontSize=max(7, int(getattr(body_style, 'fontSize', 9)) - 1),
                leading=max(9, int(getattr(body_style, 'fontSize', 9)) + 1),
            )
            head_style = ParagraphStyle(
                name='_md_tbl_head', parent=cell_style,
                fontName=(getattr(body_style, 'fontName', 'Helvetica') + '-Bold')
                    if not getattr(body_style, 'fontName', '').endswith('-Bold')
                    else getattr(body_style, 'fontName', 'Helvetica-Bold'),
                textColor=colors.white,
            )
            cols = max(len(header), max((len(r) for r in body_rows), default=0))
            def _pad(row, n):
                return row + [''] * (n - len(row)) if len(row) < n else row[:n]
            data = [[Paragraph(_md_inline_to_rl(c), head_style) for c in _pad(header, cols)]]
            for r in body_rows:
                data.append([Paragraph(_md_inline_to_rl(c), cell_style) for c in _pad(r, cols)])
            t = Table(data, repeatRows=1)
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E293B')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
                ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#CBD5E1')),
                ('LEFTPADDING', (0, 0), (-1, -1), 5),
                ('RIGHTPADDING', (0, 0), (-1, -1), 5),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]))
            flowables.append(t)
            flowables.append(Spacer(1, 4))
            continue

        # Fenced code block
        if stripped.startswith('```'):
            flush_paragraph()
            i += 1
            code_lines: list[str] = []
            while i < len(lines) and not lines[i].strip().startswith('```'):
                code_lines.append(lines[i])
                i += 1
            i += 1  # skip closing ```
            code_text = _escape_xml('\n'.join(code_lines)).replace('\n', '<br/>')
            if code_text:
                flowables.append(Paragraph(code_text, code_st))
            continue

        # Headings
        m_h = re.match(r'^(#{1,6})\s+(.*)$', stripped)
        if m_h:
            flush_paragraph()
            level = len(m_h.group(1))
            content = m_h.group(2).strip()
            size_bump = max(0, 4 - (level - 1) * 1)
            h_style = ParagraphStyle(
                name=f'_md_h{level}', parent=h_st,
                fontSize=int(getattr(body_style, 'fontSize', 9)) + size_bump,
            )
            flowables.append(Paragraph(_md_inline_to_rl(content), h_style))
            i += 1
            continue

        # Bullet / numbered list
        m_li = re.match(r'^\s*(?:[-*+]|\d+\.)\s+(.*)$', line)
        if m_li:
            flush_paragraph()
            content = m_li.group(1).strip()
            flowables.append(Paragraph(
                _md_inline_to_rl(content),
                bullet_st,
                bulletText='•',
            ))
            i += 1
            continue

        # Blockquote
        if stripped.startswith('>'):
            flush_paragraph()
            quote_lines: list[str] = []
            while i < len(lines) and lines[i].strip().startswith('>'):
                quote_lines.append(re.sub(r'^\s*>\s?', '', lines[i]))
                i += 1
            quote_text = ' '.join(l.strip() for l in quote_lines).strip()
            if quote_text:
                quote_style = ParagraphStyle(
                    name='_md_quote', parent=body_style,
                    leftIndent=12, textColor=colors.HexColor('#475569'),
                    fontName=getattr(body_style, 'fontName', 'Helvetica'),
                )
                flowables.append(Paragraph(
                    f'<i>{_md_inline_to_rl(quote_text)}</i>',
                    quote_style,
                ))
            continue

        # Blank line — paragraph break
        if not stripped:
            flush_paragraph()
            i += 1
            continue

        # Regular line — accumulate
        paragraph_buf.append(stripped)
        i += 1

    flush_paragraph()
    return flowables


def _markdown_from_html(html: str) -> str:
    if not html:
        return ""
    text = html
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
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    text = text.replace('&nbsp;', ' ')
    return text.strip()


def _decode_logo(logo_base64: str) -> Optional[io.BytesIO]:
    if not logo_base64:
        return None
    try:
        if ',' in logo_base64:
            logo_base64 = logo_base64.split(',', 1)[1]
        data = base64.b64decode(logo_base64)
        return io.BytesIO(data)
    except Exception:
        return None


def _get_page_size(name: str):
    if name and name.lower() == 'a4':
        return A4
    return letter


# ═══════════════════════════════════════════════════════════════════
# PDF Report Generator
# ═══════════════════════════════════════════════════════════════════

class PDFReportGenerator:
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
    ):
        self.engagement = engagement
        self.sections = sections
        self.findings = sorted(findings, key=lambda x: _severity_rank(x.severity), reverse=True)
        self.testcases = testcases
        self.cleanup_artifacts = cleanup_artifacts or []
        self.theme = theme
        self.storage = storage
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

    # ── Styles ────────────────────────────────────────────────────

    def _setup_custom_styles(self):
        font       = _t(self.theme, 'font_family')
        font_bold  = f'{font}-Bold' if font != 'Courier' else 'Courier-Bold'
        primary    = _t(self.theme, 'primary_color')
        dark       = _t(self.theme, 'secondary_color')
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

    # ── Header / Footer ───────────────────────────────────────────

    def _header_footer(self, canvas, doc):
        """Professional running header + footer with accent rule."""
        canvas.saveState()
        font      = _t(self.theme, 'font_family')
        primary   = _t(self.theme, 'primary_color')
        muted     = _t(self.theme, 'muted_text_color')
        footer_t  = _t(self.theme, 'footer_text')
        show_num  = _t(self.theme, 'show_page_numbers')
        W, H      = doc.pagesize

        # ── Top accent rule ────────────────
        canvas.setStrokeColor(colors.HexColor(primary))
        canvas.setLineWidth(2)
        canvas.line(54, H - 38, W - 54, H - 38)

        # Engagement name top-left
        canvas.setFont(f'{font}-Bold', 8)
        canvas.setFillColor(colors.HexColor(muted))
        canvas.drawString(54, H - 28, self.engagement.name[:60])

        # Footer rule
        canvas.setStrokeColor(colors.HexColor('#E2E8F0'))
        canvas.setLineWidth(0.5)
        canvas.line(54, 36, W - 54, 36)

        canvas.setFont(font, 8)
        canvas.setFillColor(colors.HexColor(muted))
        if footer_t:
            canvas.drawString(54, 24, footer_t)
        if show_num:
            canvas.drawRightString(W - 54, 24, f'Page {doc.page}')

        canvas.restoreState()

    def _cover_page_canvas(self, canvas, doc):
        """Dark cover page — called as onFirstPage."""
        self._draw_cover(canvas, doc)

    def _draw_cover(self, canvas, doc):
        """Draw the cover page entirely from scratch on canvas."""
        canvas.saveState()
        W, H = doc.pagesize
        font     = _t(self.theme, 'font_family')
        font_b   = f'{font}-Bold'
        cover_bg = _t(self.theme, 'cover_bg_color')
        primary  = _t(self.theme, 'primary_color')

        # ── Full dark background ───────────────────────────────────
        canvas.setFillColor(colors.HexColor(cover_bg))
        canvas.rect(0, 0, W, H, fill=1, stroke=0)

        # ── Geometric accent: top-right polygon ───────────────────
        # Large dark triangle top right
        canvas.setFillColor(colors.HexColor('#1E293B'))
        p = canvas.beginPath()
        p.moveTo(W * 0.55, H)
        p.lineTo(W, H)
        p.lineTo(W, H * 0.60)
        p.close()
        canvas.drawPath(p, fill=1, stroke=0)

        # Thin red accent slash in the top-right triangle
        canvas.setFillColor(colors.HexColor(primary))
        p2 = canvas.beginPath()
        p2.moveTo(W * 0.68, H)
        p2.lineTo(W * 0.72, H)
        p2.lineTo(W, H * 0.72)
        p2.lineTo(W, H * 0.68)
        p2.close()
        canvas.drawPath(p2, fill=1, stroke=0)

        # ── Bottom accent bar ──────────────────────────────────────
        canvas.setFillColor(colors.HexColor(primary))
        canvas.rect(0, 0, W, 6, fill=1, stroke=0)

        # Small dark band above bottom bar for classification
        canvas.setFillColor(colors.HexColor('#1E293B'))
        canvas.rect(0, 6, W, 52, fill=1, stroke=0)

        # Classification label
        canvas.setFillColor(colors.HexColor(primary))
        canvas.setFont(font_b, 8)
        _t_classify = _t(self.theme, 'footer_text') or 'CONFIDENTIAL'
        canvas.drawCentredString(W / 2, 26, f'● {_t_classify.upper()} ●')

        # Date bottom-right inside band
        canvas.setFillColor(colors.HexColor('#94A3B8'))
        canvas.setFont(font, 8)
        canvas.drawRightString(W - 54, 26, datetime.now().strftime('%B %d, %Y'))

        # ── Red accent rule (horizontal) ───────────────────────────
        accent_y = H * 0.45
        canvas.setStrokeColor(colors.HexColor(primary))
        canvas.setLineWidth(2)
        canvas.line(54, accent_y, W * 0.5, accent_y)

        # ── Logo ───────────────────────────────────────────────────
        logo_data = _t(self.theme, 'logo_base64')
        logo_top = H * 0.80
        if logo_data:
            logo_stream = _decode_logo(logo_data)
            if logo_stream:
                try:
                    from reportlab.platypus import Image as RLImage
                    img = RLImage(logo_stream, width=1.6 * inch, height=0.8 * inch)
                    img.drawOn(canvas, 54, logo_top)
                except Exception:
                    pass

        # ── Report title ───────────────────────────────────────────
        cover_title = _t(self.theme, 'cover_title') or 'Red Team Assessment Report'
        # Split into two lines if long
        canvas.setFillColor(colors.white)
        canvas.setFont(font_b, 34)
        # Wrap at 30 chars
        words = cover_title.split()
        line1, line2 = [], []
        for w in words:
            if len(' '.join(line1 + [w])) <= 28:
                line1.append(w)
            else:
                line2.append(w)
        y_title = H * 0.60
        if line2:
            canvas.drawString(54, y_title + 20, ' '.join(line1))
            canvas.drawString(54, y_title - 18, ' '.join(line2))
        else:
            canvas.drawString(54, y_title, cover_title)

        # ── Engagement name ────────────────────────────────────────
        canvas.setFillColor(colors.HexColor('#CBD5E1'))
        canvas.setFont(font_b, 14)
        canvas.drawString(54, H * 0.38, self.engagement.name)

        # ── Client name ────────────────────────────────────────────
        canvas.setFillColor(colors.HexColor('#94A3B8'))
        canvas.setFont(font, 11)
        client_line = f'CLIENT: {(self.engagement.client_name or "").upper()}'
        canvas.drawString(54, H * 0.34, client_line)

        # ── Engagement type / status ───────────────────────────────
        eng_type = _v(getattr(self.engagement, 'engagement_type', None))
        if eng_type and eng_type != 'N/A':
            canvas.setFont(font, 9)
            canvas.setFillColor(colors.HexColor('#64748B'))
            canvas.drawString(54, H * 0.31, eng_type.replace('_', ' ').upper())

        canvas.restoreState()

    # ── Table of Contents ─────────────────────────────────────────

    def _render_toc(self, elements):
        font      = _t(self.theme, 'font_family')
        font_b    = f'{font}-Bold'
        dark      = _t(self.theme, 'secondary_color')
        body_c    = _t(self.theme, 'body_text_color')
        muted_c   = _t(self.theme, 'muted_text_color')

        # Section title bar
        elements.append(self._section_header_table('TABLE OF CONTENTS'))
        elements.append(Spacer(1, 16))

        toc_items = []
        for i, section in enumerate(self.sections, 1):
            row = [
                Paragraph(f'{i}.  {_escape_xml(section.title)}', ParagraphStyle(
                    name=f'TOC_{i}',
                    parent=self.styles['TOCEntry'],
                    fontName=font_b if i == 1 else font,
                )),
                Paragraph('· · · · · · · · · · · · · · · · · · · ·', ParagraphStyle(
                    name=f'TOC_dots_{i}',
                    parent=self.styles['TOCEntry'],
                    textColor=colors.HexColor(muted_c),
                    alignment=1,
                )),
            ]
            toc_items.append(row)

        if toc_items:
            toc_table = Table(toc_items, colWidths=[3.5 * inch, None])
            toc_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                ('LINEBELOW', (0, 0), (-1, -2), 0.25, colors.HexColor('#E2E8F0')),
            ]))
            elements.append(toc_table)

        elements.append(PageBreak())

    # ── Section header helper ─────────────────────────────────────

    def _section_header_table(self, title: str) -> Table:
        """Returns a dark full-width header bar with white title."""
        dark    = _t(self.theme, 'secondary_color')
        primary = _t(self.theme, 'primary_color')
        font    = _t(self.theme, 'font_family')
        font_b  = f'{font}-Bold'

        cell = Paragraph(_escape_xml(title), self.styles['SectionTitle'])
        t = Table([[cell]], colWidths=[6.5 * inch])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(dark)),
            ('LEFTPADDING', (0, 0), (-1, -1), 14),
            ('RIGHTPADDING', (0, 0), (-1, -1), 14),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
            ('LINEABOVE', (0, 0), (-1, 0), 3, colors.HexColor(primary)),
        ]))
        return t

    # ── Severity chart ────────────────────────────────────────────

    def _severity_summary_table(self, severity_counts: dict) -> Table:
        """Horizontal mini-bar chart as a styled table."""
        font   = _t(self.theme, 'font_family')
        font_b = f'{font}-Bold'
        max_count = max((severity_counts.get(s, 0) for s in _SEV_COLORS), default=1) or 1
        bar_max_w = 180  # points

        rows = []
        for sev, hex_col in _SEV_COLORS.items():
            count = severity_counts.get(sev, 0)
            bar_w = max(4, int((count / max_count) * bar_max_w)) if count > 0 else 0

            # Severity label
            label_cell = Paragraph(sev, ParagraphStyle(
                name=f'sev_{sev}',
                parent=self.styles['Normal'],
                fontSize=9, fontName=font_b,
                textColor=colors.HexColor(hex_col),
            ))

            # Bar: a tiny coloured inner table
            if bar_w > 0:
                bar_inner = Table([['']], colWidths=[bar_w])
                bar_inner.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(hex_col)),
                    ('TOPPADDING', (0, 0), (-1, -1), 7),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
                ]))
            else:
                bar_inner = Paragraph('', self.styles['Normal'])

            count_cell = Paragraph(str(count), ParagraphStyle(
                name=f'cnt_{sev}',
                parent=self.styles['Normal'],
                fontSize=11, fontName=font_b,
                textColor=colors.HexColor(hex_col),
                alignment=1,
            ))

            rows.append([label_cell, bar_inner, count_cell])

        t = Table(rows, colWidths=[1.1 * inch, bar_max_w, 0.5 * inch])
        t.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
            ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
            ('LINEBELOW', (0, 0), (-1, -2), 0.25, colors.HexColor('#E2E8F0')),
        ]))
        return t

    # ── Finding card ──────────────────────────────────────────────

    def _finding_card(self, idx: int, finding: Finding) -> Table:
        """A bordered card for a single finding."""
        sev_str   = _v(finding.severity).upper()
        sev_hex   = _SEV_COLORS.get(sev_str, '#64748B')
        sev_bg    = _SEV_BG_COLORS.get(sev_str, '#F8FAFC')
        font      = _t(self.theme, 'font_family')
        font_b    = f'{font}-Bold'
        body_c    = _t(self.theme, 'body_text_color')
        muted_c   = _t(self.theme, 'muted_text_color')
        dark      = _t(self.theme, 'secondary_color')

        elements = []

        # -- Header row: number + title + severity badge
        title_text = Paragraph(
            f'<font color="{sev_hex}">F{idx:02d}</font>  '
            f'{_escape_xml(finding.title)}',
            ParagraphStyle(
                name=f'FT_{idx}', parent=self.styles['FindingTitle'],
                textColor=colors.white, fontSize=11, fontName=font_b, leading=15,
            )
        )
        badge = Paragraph(
            sev_str,
            ParagraphStyle(
                name=f'Badge_{idx}', parent=self.styles['Normal'],
                fontSize=9, fontName=font_b,
                textColor=colors.HexColor(sev_hex),
                backColor=colors.white,
                alignment=1,
            )
        )
        header_t = Table([[title_text, badge]], colWidths=[5.2 * inch, 1.2 * inch])
        header_t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(dark)),
            ('LEFTPADDING', (0, 0), (0, 0), 14),
            ('RIGHTPADDING', (0, 0), (0, 0), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 9),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (1, 0), (1, 0), 'CENTER'),
            ('BACKGROUND', (1, 0), (1, 0), colors.HexColor(sev_bg)),
            ('LINEBEFORE', (0, 0), (0, 0), 5, colors.HexColor(sev_hex)),
        ]))
        elements.append(header_t)

        # -- Body: details in a clean two-section layout
        body_rows = []

        def _label_para(label):
            return Paragraph(label, ParagraphStyle(
                name=f'L_{label}_{idx}', parent=self.styles['Label'],
                fontName=font_b, fontSize=8,
                textColor=colors.HexColor(muted_c),
            ))

        def _add_row(label, value):
            """Plain (non-markdown) row — used for short scalar values."""
            if not value:
                return
            body_rows.append([
                _label_para(label),
                Paragraph(_escape_xml(str(value)[:800]), ParagraphStyle(
                    name=f'V_{label}_{idx}', parent=self.styles['BodyText2'],
                    fontSize=9, textColor=colors.HexColor(body_c),
                )),
            ])

        def _add_md_row(label, value, max_chars=4000):
            """Markdown row — renders block-level markdown into the cell."""
            if not value:
                return
            cell_body_style = ParagraphStyle(
                name=f'V_{label}_{idx}', parent=self.styles['BodyText2'],
                fontSize=9, textColor=colors.HexColor(body_c),
                spaceAfter=2,
            )
            flowables = _md_to_flowables(
                str(value), cell_body_style, max_chars=max_chars,
                image_resolver=self._resolve_markdown_image,
                max_image_width=4.5 * inch, max_image_height=3.0 * inch,
            )
            if not flowables:
                return
            body_rows.append([_label_para(label), flowables])

        asset_names = ', '.join([a.name for a in finding.assets]) if finding.assets else 'N/A'
        _add_row('AFFECTED ASSETS', asset_names)
        if finding.cvss_score is not None:
            cvss_label = f'{finding.cvss_score}'
            if finding.cvss_vector:
                cvss_label += f'  |  {finding.cvss_vector}'
            _add_row('CVSS', cvss_label)

        _add_md_row('DESCRIPTION', finding.description)
        _add_md_row('IMPACT', finding.impact)
        _add_md_row('STEPS TO REPRODUCE', finding.steps_to_reproduce)
        _add_md_row('RECOMMENDATIONS', finding.mitigations)
        _add_md_row('REFERENCES', finding.references)

        if body_rows:
            body_t = Table(body_rows, colWidths=[1.3 * inch, 5.1 * inch])
            body_t.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('LEFTPADDING', (0, 0), (0, -1), 14),
                ('LEFTPADDING', (1, 0), (1, -1), 8),
                ('RIGHTPADDING', (1, 0), (1, -1), 8),
                ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
                ('LINEBELOW', (0, 0), (-1, -2), 0.25, colors.HexColor('#E2E8F0')),
                ('LINEBEFORE', (0, 0), (0, -1), 5, colors.HexColor(sev_hex)),
            ]))
            elements.append(body_t)
        else:
            elements.append(Spacer(1, 8))

        card = Table([[e] for e in elements], colWidths=[6.5 * inch])
        card.setStyle(TableStyle([
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
        ]))
        return card

    # ── Generate ──────────────────────────────────────────────────

    def generate(self) -> bytes:
        buffer   = io.BytesIO()
        page_size = _get_page_size(_t(self.theme, 'page_size'))
        doc = SimpleDocTemplate(
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

        # Sections
        for section in self.sections:
            if section.section_type == SectionType.TEXT:
                self._render_text_section(elements, section)
            elif section.section_type == SectionType.FINDINGS:
                self._render_findings_section(elements, section)
            elif section.section_type == SectionType.TESTCASES:
                self._render_testcases_section(elements, section)
            elif section.section_type == SectionType.CLEANUP_ARTIFACTS:
                self._render_cleanup_artifacts_section(elements, section)

        # Choose which first-page callback to use
        if show_cover:
            first_page_cb = self._cover_and_header
        else:
            first_page_cb = self._header_footer

        doc.build(elements, onFirstPage=first_page_cb, onLaterPages=self._header_footer)
        pdf_value = buffer.getvalue()
        buffer.close()
        return pdf_value

    def _cover_and_header(self, canvas, doc):
        """On the very first page, draw the cover; rely on platypus for the rest."""
        canvas.saveState()
        self._draw_cover(canvas, doc)
        canvas.restoreState()

    # ── Section renderers ─────────────────────────────────────────

    def _render_text_section(self, elements, section: ReportSection):
        elements.append(self._section_header_table(section.title.upper()))
        elements.append(Spacer(1, 14))
        if section.content:
            for fl in _md_to_flowables(
                section.content, self.styles['BodyText2'],
                image_resolver=self._resolve_markdown_image,
            ):
                elements.append(fl)
        elements.append(Spacer(1, 20))

    def _render_findings_section(self, elements, section: ReportSection):
        elements.append(self._section_header_table(section.title.upper()))
        elements.append(Spacer(1, 16))

        if not self.findings:
            elements.append(Paragraph('No findings recorded for this engagement.', self.styles['BodyText2']))
            elements.append(Spacer(1, 12))
            return

        # ── Severity overview ──────────────────────────────────────
        severity_counts = {}
        for f in self.findings:
            key = _v(f.severity).upper()
            severity_counts[key] = severity_counts.get(key, 0) + 1

        elements.append(Paragraph('Severity Distribution', self.styles['SubSectionTitle']))
        elements.append(self._severity_summary_table(severity_counts))
        elements.append(Spacer(1, 24))

        # ── Finding details ────────────────────────────────────────
        elements.append(Paragraph('Detailed Findings', self.styles['SubSectionTitle']))
        elements.append(Spacer(1, 8))

        for idx, finding in enumerate(self.findings, 1):
            card = self._finding_card(idx, finding)
            elements.append(KeepTogether(card))
            elements.append(Spacer(1, 8))
            self._render_evidence(elements, finding)
            elements.append(Spacer(1, 12))

    # ── Evidence helpers ──────────────────────────────────────────

    def _fetch_file_bytes(self, filename: str) -> Optional[bytes]:
        """Synchronously download a file from MinIO via the underlying boto3 client."""
        if self.storage is None:
            return None
        try:
            buf = io.BytesIO()
            self.storage.s3.download_fileobj(self.storage.bucket_name, filename, buf)
            return buf.getvalue()
        except Exception as exc:
            _log.warning(f'Could not fetch evidence file {filename!r}: {exc}')
            return None

    _IMAGE_MIMES = {'image/png', 'image/jpeg', 'image/gif', 'image/webp', 'image/bmp'}

    def _render_evidence(self, elements, finding: Finding):
        """Embed images and list non-image attachments beneath a finding card."""
        evidence_list = [e for e in (finding.evidence or []) if e.include_in_report]
        if not evidence_list:
            return

        font    = _t(self.theme, 'font_family')
        font_b  = f'{font}-Bold'
        muted   = _t(self.theme, 'muted_text_color')
        page_w  = 6.5 * inch
        max_img_h = 4.0 * inch

        # Section label
        ev_hdr = Table(
            [[Paragraph('EVIDENCE & ATTACHMENTS', ParagraphStyle(
                name='EvidenceHdrLabel', parent=self.styles['Normal'],
                fontSize=8, fontName=font_b,
                textColor=colors.HexColor(muted), letterSpacing=1,
            ))]],
            colWidths=[page_w],
        )
        ev_hdr.setStyle(TableStyle([
            ('TOPPADDING',    (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING',   (0, 0), (-1, -1), 0),
            ('LINEABOVE',     (0, 0), (-1, 0), 0.5, colors.HexColor('#E2E8F0')),
        ]))
        elements.append(ev_hdr)

        for ev in evidence_list:
            mime = (ev.mime_type or '').lower()
            # Build caption
            caption_parts = []
            if ev.description:
                caption_parts.append(ev.description)
            caption_parts.append(f'[{ev.original_filename}]')
            caption_text = _escape_xml('  '.join(caption_parts))

            if mime in self._IMAGE_MIMES and self.storage:
                file_bytes = self._fetch_file_bytes(ev.filename)
                if file_bytes:
                    try:
                        img_stream = io.BytesIO(file_bytes)
                        img = Image(img_stream)
                        iw, ih = img.imageWidth, img.imageHeight
                        if iw and ih:
                            scale = min(page_w / iw, max_img_h / ih, 1.0)
                            img.drawWidth  = iw * scale
                            img.drawHeight = ih * scale
                        img.hAlign = 'CENTER'
                        elements.append(img)
                        elements.append(Paragraph(caption_text, ParagraphStyle(
                            name=f'ImgCap_{ev.id}', parent=self.styles['Caption'],
                            alignment=1, spaceAfter=6,
                        )))
                        elements.append(Spacer(1, 4))
                        continue
                    except Exception as exc:
                        _log.warning(f'Could not embed image {ev.filename!r}: {exc}')

            # Non-image or failed image → text attachment reference
            elements.append(Paragraph(
                f'\U0001f4ce  {caption_text}',
                ParagraphStyle(
                    name=f'AttachRef_{ev.id}', parent=self.styles['BodyText2'],
                    fontSize=9, textColor=colors.HexColor(muted), spaceAfter=4,
                    alignment=1,
                ),
            ))

    # ── Table section renderers ───────────────────────────────────

    def _render_testcases_section(self, elements, section: ReportSection):
        elements.append(self._section_header_table(section.title.upper()))
        elements.append(Spacer(1, 16))

        if not self.testcases:
            elements.append(Paragraph('No test cases recorded.', self.styles['BodyText2']))
            elements.append(Spacer(1, 12))
            return

        font   = _t(self.theme, 'font_family')
        font_b = f'{font}-Bold'
        dark   = _t(self.theme, 'secondary_color')

        header_style = ParagraphStyle(
            name='TCHeader', parent=self.styles['Normal'],
            fontSize=9, fontName=font_b, textColor=colors.white,
        )
        cell_style = ParagraphStyle(
            name='TCCell', parent=self.styles['Normal'],
            fontSize=9, fontName=font, textColor=colors.HexColor(_t(self.theme, 'body_text_color')),
        )

        rows = [[
            Paragraph('TEST CASE', header_style),
            Paragraph('CATEGORY', header_style),
            Paragraph('EXECUTED', header_style),
            Paragraph('RESULT', header_style),
        ]]
        for tc in self.testcases:
            executed = '✓' if tc.is_executed else '–'
            result   = '✓ Pass' if tc.is_successful else ('✗ Fail' if tc.is_successful is False else 'N/A')
            rows.append([
                Paragraph(_escape_xml(tc.title[:80]), cell_style),
                Paragraph(_v(tc.category).replace('_', ' ').title(), cell_style),
                Paragraph(executed, cell_style),
                Paragraph(result, cell_style),
            ])

        col_widths = [3.0 * inch, 1.4 * inch, 0.85 * inch, 1.0 * inch]
        t = Table(rows, colWidths=col_widths, repeatRows=1)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(dark)),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (2, 1), (-1, -1), 'CENTER'),
            ('TOPPADDING', (0, 0), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
            ('LINEBELOW', (0, 0), (-1, -1), 0.25, colors.HexColor('#E2E8F0')),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 20))

    def _render_cleanup_artifacts_section(self, elements, section: ReportSection):
        elements.append(self._section_header_table(section.title.upper()))
        elements.append(Spacer(1, 16))

        if not self.cleanup_artifacts:
            elements.append(Paragraph('No cleanup artifacts recorded.', self.styles['BodyText2']))
            elements.append(Spacer(1, 12))
            return

        font   = _t(self.theme, 'font_family')
        font_b = f'{font}-Bold'
        dark   = _t(self.theme, 'secondary_color')

        header_style = ParagraphStyle(
            name='CAHeader', parent=self.styles['Normal'],
            fontSize=9, fontName=font_b, textColor=colors.white,
        )
        cell_style = ParagraphStyle(
            name='CACell', parent=self.styles['Normal'],
            fontSize=9, fontName=font, textColor=colors.HexColor(_t(self.theme, 'body_text_color')),
        )

        rows = [[
            Paragraph('ARTIFACT', header_style),
            Paragraph('TYPE', header_style),
            Paragraph('STATUS', header_style),
            Paragraph('LOCATION', header_style),
        ]]
        for ca in self.cleanup_artifacts:
            rows.append([
                Paragraph(_escape_xml(ca.title[:60]), cell_style),
                Paragraph(_v(ca.artifact_type).replace('_', ' ').title(), cell_style),
                Paragraph(_v(ca.status).replace('_', ' ').title(), cell_style),
                Paragraph(_escape_xml((ca.location or 'N/A')[:50]), cell_style),
            ])

        col_widths = [2.3 * inch, 1.3 * inch, 1.2 * inch, 1.7 * inch]
        t = Table(rows, colWidths=col_widths, repeatRows=1)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(dark)),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
            ('LINEBELOW', (0, 0), (-1, -1), 0.25, colors.HexColor('#E2E8F0')),
        ]))
        elements.append(t)

        # Detailed entries
        elements.append(Spacer(1, 24))
        for idx, ca in enumerate(self.cleanup_artifacts, 1):
            det_rows = []

            def _label(label):
                return Paragraph(label, ParagraphStyle(
                    name=f'CAL_{idx}_{label}', parent=self.styles['Label'],
                    fontSize=8, fontName=font_b,
                    textColor=colors.HexColor(_t(self.theme, 'muted_text_color')),
                ))

            def _add(label, val):
                """Plain row — short scalar values."""
                if not val:
                    return
                det_rows.append([
                    _label(label),
                    Paragraph(_escape_xml(str(val)[:600]), ParagraphStyle(
                        name=f'CAV_{idx}_{label}', parent=self.styles['BodyText2'],
                        fontSize=9,
                    )),
                ])

            def _add_md(label, val, max_chars=3000):
                """Markdown row — renders block-level markdown into the cell."""
                if not val:
                    return
                cell_style = ParagraphStyle(
                    name=f'CAV_{idx}_{label}', parent=self.styles['BodyText2'],
                    fontSize=9, spaceAfter=2,
                )
                flowables = _md_to_flowables(
                    str(val), cell_style, max_chars=max_chars,
                    image_resolver=self._resolve_markdown_image,
                    max_image_width=4.5 * inch, max_image_height=3.0 * inch,
                )
                if not flowables:
                    return
                det_rows.append([_label(label), flowables])

            _add('TYPE', _v(ca.artifact_type).replace('_', ' ').title())
            _add('STATUS', _v(ca.status).replace('_', ' ').title())
            if ca.location:
                _add('LOCATION', ca.location)
            _add_md('DESCRIPTION', ca.description)
            _add_md('CLEANUP NOTES', ca.cleanup_notes)
            assets = ', '.join([a.name for a in ca.assets]) if ca.assets else None
            if assets:
                _add('ASSETS', assets)

            if det_rows:
                header = Table(
                    [[Paragraph(f'{idx}. {_escape_xml(ca.title)}', ParagraphStyle(
                        name=f'CATitle_{idx}', parent=self.styles['FindingTitle'],
                        fontSize=10,
                    ))]],
                    colWidths=[6.5 * inch],
                )
                header.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(dark)),
                    ('LEFTPADDING', (0, 0), (-1, -1), 14),
                    ('TOPPADDING', (0, 0), (-1, -1), 8),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                    ('LINEBEFORE', (0, 0), (0, 0), 4, colors.HexColor(_t(self.theme, 'primary_color'))),
                ]))
                body_t = Table(det_rows, colWidths=[1.3 * inch, 5.2 * inch])
                body_t.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('TOPPADDING', (0, 0), (-1, -1), 6),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                    ('LEFTPADDING', (0, 0), (0, -1), 14),
                    ('LEFTPADDING', (1, 0), (1, -1), 8),
                    ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
                    ('LINEBELOW', (0, 0), (-1, -2), 0.25, colors.HexColor('#E2E8F0')),
                    ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
                ]))
                elements.append(KeepTogether([header, body_t]))
                elements.append(Spacer(1, 12))


# ═══════════════════════════════════════════════════════════════════
# Markdown Report Generator (unchanged)
# ═══════════════════════════════════════════════════════════════════

class MarkdownReportGenerator:
    def __init__(
        self,
        engagement: Engagement,
        sections: List[ReportSection],
        findings: List[Finding],
        testcases: List[TestCase],
        cleanup_artifacts: List[CleanupArtifact] = None,
        theme: Optional[ReportTheme] = None,
    ):
        self.engagement = engagement
        self.sections = sections
        self.findings = sorted(findings, key=lambda x: _severity_rank(x.severity), reverse=True)
        self.testcases = testcases
        self.cleanup_artifacts = cleanup_artifacts or []
        self.theme = theme

    def generate(self) -> str:
        parts = []
        cover_title = _t(self.theme, 'cover_title')
        parts.append(f'# {cover_title}: {self.engagement.name}\n')
        parts.append(f'**Client:** {self.engagement.client_name}  ')
        parts.append(f'**Date:** {datetime.now().strftime("%B %d, %Y")}\n')
        parts.append('---\n')

        for section in self.sections:
            if section.section_type == SectionType.TEXT:
                parts.append(self._render_text_section(section))
            elif section.section_type == SectionType.FINDINGS:
                parts.append(self._render_findings_section(section))
            elif section.section_type == SectionType.TESTCASES:
                parts.append(self._render_testcases_section(section))
            elif section.section_type == SectionType.CLEANUP_ARTIFACTS:
                parts.append(self._render_cleanup_artifacts_section(section))

        return '\n'.join(parts)

    def _render_text_section(self, section: ReportSection) -> str:
        md = f'## {section.title}\n\n'
        content = _markdown_from_html(section.content) if section.content else ''
        if content:
            md += content + '\n'
        md += '\n'
        return md

    def _render_findings_section(self, section: ReportSection) -> str:
        md = f'## {section.title}\n\n'

        if not self.findings:
            md += 'No findings recorded.\n\n'
            return md

        severity_counts = {}
        for f in self.findings:
            sev_key = _v(f.severity)
            severity_counts[sev_key] = severity_counts.get(sev_key, 0) + 1

        md += '### Severity Summary\n\n'
        md += '| Severity | Count |\n|----------|-------|\n'
        for s in Severity:
            md += f'| {_v(s)} | {severity_counts.get(_v(s), 0)} |\n'
        md += '\n'

        for idx, finding in enumerate(self.findings):
            md += f'### Finding {idx + 1}: {finding.title}\n\n'
            md += f'- **Severity:** {_v(finding.severity)}\n'

            asset_names = ', '.join([a.name for a in finding.assets]) if finding.assets else 'N/A'
            md += f'- **Affected Asset(s):** {asset_names}\n'

            if finding.cvss_score is not None:
                md += f'- **CVSS Score:** {finding.cvss_score}\n'

            md += f'\n#### Description\n\n{_markdown_from_html(finding.description)}\n\n'

            if finding.impact:
                md += f'#### Impact\n\n{_markdown_from_html(finding.impact)}\n\n'

            if finding.steps_to_reproduce:
                md += f'#### Steps to Reproduce\n\n{_markdown_from_html(finding.steps_to_reproduce)}\n\n'

            if finding.mitigations:
                md += f'#### Mitigations\n\n{_markdown_from_html(finding.mitigations)}\n\n'

            if finding.references:
                md += f'#### References\n\n{_markdown_from_html(finding.references)}\n\n'

            md += '---\n\n'

        return md

    def _render_testcases_section(self, section: ReportSection) -> str:
        md = f'## {section.title}\n\n'

        if not self.testcases:
            md += 'No test cases recorded.\n\n'
            return md

        md += '| Title | Category | Executed | Result |\n'
        md += '|-------|----------|----------|--------|\n'

        for tc in self.testcases:
            executed = 'Yes' if tc.is_executed else 'No'
            result = 'Pass' if tc.is_successful else ('Fail' if tc.is_successful is False else 'N/A')
            category = _v(tc.category).replace('_', ' ').title()
            md += f'| {tc.title} | {category} | {executed} | {result} |\n'

        md += '\n'
        return md

    def _render_cleanup_artifacts_section(self, section: ReportSection) -> str:
        md = f'## {section.title}\n\n'

        if not self.cleanup_artifacts:
            md += 'No cleanup artifacts recorded.\n\n'
            return md

        md += '| Title | Type | Status | Location |\n'
        md += '|-------|------|--------|----------|\n'

        for ca in self.cleanup_artifacts:
            artifact_type = _v(ca.artifact_type).replace('_', ' ').title()
            status_val = _v(ca.status).replace('_', ' ').title()
            location = ca.location or 'N/A'
            md += f'| {ca.title} | {artifact_type} | {status_val} | {location} |\n'

        md += '\n'

        for idx, ca in enumerate(self.cleanup_artifacts):
            md += f'### {idx + 1}. {ca.title}\n\n'
            md += f'- **Type:** {_v(ca.artifact_type).replace("_", " ").title()}\n'
            md += f'- **Status:** {_v(ca.status).replace("_", " ").title()}\n'

            if ca.location:
                md += f'- **Location:** {ca.location}\n'

            if ca.description:
                md += f'\n#### Description\n\n{_markdown_from_html(ca.description)}\n\n'

            if ca.cleanup_notes:
                md += f'#### Cleanup Notes\n\n{_markdown_from_html(ca.cleanup_notes)}\n\n'

            asset_names = ', '.join([a.name for a in ca.assets]) if ca.assets else None
            if asset_names:
                md += f'- **Affected Asset(s):** {asset_names}\n'

            md += '\n---\n\n'

        return md
