import io
import logging
import base64
import math

_log = logging.getLogger(__name__)
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image, HRFlowable, KeepTogether
from reportlab.platypus.tableofcontents import TableOfContents
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
from utils.marking import MarkingEngine, MarkedImage
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

    # Severity (themeable — promoted from the _SEV_COLORS constants below)
    "severity_critical_color": "#DC2626",
    "severity_high_color":     "#EA580C",
    "severity_medium_color":   "#D97706",
    "severity_low_color":      "#2563EB",
    "severity_info_color":     "#64748B",

    # Table style tokens
    "table_zebra_enabled": True,
    "table_alt_row_bg":    "#F8FAFC",
    "table_grid_color":    "#CBD5E1",

    # Header / footer zones + page numbering
    "show_page_x_of_y":    False,

    # Cover
    "cover_template":      "banded",

    # Evidence
    "show_evidence_filenames": True,

    # Finding card styling
    "show_finding_severity_bar": True,
    "show_section_title_background": True,

    # Logo
    "logo_scale": 100,   # percent of the base height; aspect ratio preserved
}

# Order findings/severity summaries are rendered in (most → least severe).
_SEV_ORDER = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]

# Map a severity to its themeable color key (falls back via _DEFAULTS).
_SEV_THEME_KEY = {
    "CRITICAL": "severity_critical_color",
    "HIGH":     "severity_high_color",
    "MEDIUM":   "severity_medium_color",
    "LOW":      "severity_low_color",
    "INFO":     "severity_info_color",
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
    mark_text: Optional[str] = None,
    mark_anchors=None,
    mark_fg: str = '#B91C1C',
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
            # Inline images inherit the parent's effective mark. They have no
            # caption, so a CAPTION-only policy still stamps a corner (TOP_LEFT)
            # so the image carries its mark.
            overlay = [a for a in (mark_anchors or []) if a != 'CAPTION']
            if mark_text and not overlay:
                overlay = ['TOP_LEFT']
            if mark_text and overlay:
                img = MarkedImage(buf, mark_text=mark_text, anchors=overlay, mark_fg=mark_fg)
            else:
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

class _OutlineDocTemplate(SimpleDocTemplate):
    """SimpleDocTemplate that registers a PDF outline (bookmark) entry for any
    flowable tagged with `_outline_label`, so the reader's navigation pane is
    populated. Optional `_outline_level` nests entries."""

    def afterFlowable(self, flowable):
        label = getattr(flowable, '_outline_label', None)
        if not label:
            return
        level = getattr(flowable, '_outline_level', 0)
        key = f'sec-{id(flowable)}'
        try:
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(label, key, level=level, closed=False)
            # Feed the TableOfContents (resolved over multiBuild passes).
            self.notify('TOCEntry', (level, label, self.page, key))
        except Exception:
            pass


def _make_numbered_canvas(font_name: str, color_hex: str, skip_first: bool):
    """Canvas subclass that stamps 'Page X of Y' once the total page count is
    known (second save pass). `skip_first` omits the number on the cover."""
    class NumberedCanvas(pdfcanvas.Canvas):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._saved_states = []

        def showPage(self):
            self._saved_states.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._saved_states)
            for idx, state in enumerate(self._saved_states):
                self.__dict__.update(state)
                if not (skip_first and idx == 0):
                    self._draw_page_number(idx + 1, total)
                pdfcanvas.Canvas.showPage(self)
            pdfcanvas.Canvas.save(self)

        def _draw_page_number(self, page_num, total):
            W = self._pagesize[0]
            self.saveState()
            self.setFont(font_name, 8)
            self.setFillColor(colors.HexColor(color_hex))
            self.drawRightString(W - 54, 24, f'Page {page_num} of {total}')
            self.restoreState()

    return NumberedCanvas


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
        marking_profile=None,
    ):
        self.engagement = engagement
        self.sections = sections
        self.findings = sorted(findings, key=lambda x: _severity_rank(x.severity), reverse=True)
        self.testcases = testcases
        self.cleanup_artifacts = cleanup_artifacts or []
        self.theme = theme
        self.storage = storage
        # Portion marking — None when no profile is selected (marking disabled).
        self.marking = MarkingEngine(marking_profile, engagement) if marking_profile else None
        # Document banner level (high-water mark), computed in generate().
        self._banner_level = None
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

    # ── Portion marking helpers ───────────────────────────────────

    def _eff_mark(self, entity):
        """Effective (level, suffix) for an entity; (None, None) if marking off."""
        if not self.marking:
            return (None, None)
        return self.marking.resolve(
            getattr(entity, 'classification_level', None),
            getattr(entity, 'classification_suffix', None),
        )

    def _mark_str(self, entity) -> str:
        """XML-escaped portion-mark token for an entity ('' if marking off)."""
        if not self.marking:
            return ''
        lvl, suf = self._eff_mark(entity)
        return _escape_xml(self.marking.portion_mark(lvl, suf))

    def _mark_prefix(self, entity) -> str:
        """Portion mark + trailing space, for prefixing a title/header."""
        m = self._mark_str(entity)
        return f'{m} ' if m else ''

    def _static_mark(self):
        """(level, suffix) for structural/static headings: the lowest level
        (e.g. (U)/TLP:CLEAR) by default, or the engagement default if the
        profile's static_heading_marks is 'INHERIT'."""
        if not self.marking:
            return (None, None)
        if self.marking.static_heading_mode == 'INHERIT':
            return self.marking.resolve(None, None)
        return (self.marking.lowest_level(), None)

    def _heading_mark_token(self, section=None) -> str:
        """Raw portion-mark token for a heading. An explicitly-marked section
        wins; else the static-heading mark (U by default). '' if marking off."""
        if not self.marking:
            return ''
        if section is not None and getattr(section, 'classification_level', None):
            lvl, suf = self.marking.resolve(section.classification_level, section.classification_suffix)
        else:
            lvl, suf = self._static_mark()
        return self.marking.portion_mark(lvl, suf)

    def _heading_mark_prefix(self, section=None) -> str:
        """Escaped mark prefix (+ trailing space) for a heading Paragraph."""
        tok = self._heading_mark_token(section)
        return f'{_escape_xml(tok)} ' if tok else ''

    def _eff_mark_evidence(self, ev, finding):
        """Evidence inherits the owning finding's effective mark when it has no
        explicit mark of its own (then engagement default → ceiling)."""
        if not self.marking:
            return (None, None)
        if getattr(ev, 'classification_level', None):
            return self.marking.resolve(ev.classification_level, ev.classification_suffix)
        return self._eff_mark(finding)

    def _mark_fg(self, level) -> str:
        """Banner color for a level — used to tint image stamps."""
        if self.marking and level:
            b = self.marking.banner(level)
            if b:
                return b[1]
        return '#B91C1C'

    def _table_style_tokens(self):
        """(zebra_enabled, alt_row_bg Color, grid Color) from the theme."""
        zebra = _t(self.theme, 'table_zebra_enabled')
        return (
            True if zebra is None else bool(zebra),
            colors.HexColor(_t(self.theme, 'table_alt_row_bg')),
            colors.HexColor(_t(self.theme, 'table_grid_color')),
        )

    def _table_mark_flowables(self, marks):
        """(above, below) small mark-line flowables for a table.

        `marks` is a list of (level, suffix) pairs (one per row/portion). The
        table-level mark is the highest-ranked portion, *carrying its suffix*
        (e.g. (S//SAR/TEST), not just (S))."""
        if not self.marking or not self.marking.table_anchors:
            return [], []
        best, best_rank = None, -1
        for lvl, suf in marks:
            if not lvl:
                continue
            r = self.marking._rank(lvl)
            if r > best_rank:
                best, best_rank = (lvl, suf), r
        if not best:
            return [], []
        top, top_suf = best
        mark = _escape_xml(self.marking.portion_mark(top, top_suf))
        font_b = f"{_t(self.theme, 'font_family')}-Bold"
        align_map = {'LEFT': 0, 'CENTER': 1, 'RIGHT': 2}
        above, below, seen = [], [], set()
        for anchor in self.marking.table_anchors:
            vert, horiz = ('BOTTOM', 'RIGHT') if anchor == 'CAPTION' else tuple(anchor.split('_'))
            if (vert, horiz) in seen:
                continue
            seen.add((vert, horiz))
            style = ParagraphStyle(
                name=f'_tblmk_{vert}_{horiz}', parent=self.styles['Small'],
                fontName=font_b, fontSize=8, alignment=align_map.get(horiz, 2),
                textColor=colors.HexColor(self._mark_fg(top)),
            )
            (above if vert == 'TOP' else below).append(Paragraph(mark, style))
        return above, below

    def _anchor_mark_lines(self, mark_raw, anchors, fg):
        """(above, below) mark-line Paragraphs for a single object's (image's)
        non-CAPTION anchors, drawn *outside* the object so they don't overlap it."""
        if not mark_raw:
            return [], []
        mark = _escape_xml(mark_raw)
        font_b = f"{_t(self.theme, 'font_family')}-Bold"
        align_map = {'LEFT': 0, 'CENTER': 1, 'RIGHT': 2}
        above, below, seen = [], [], set()
        for a in anchors:
            if a == 'CAPTION':
                continue
            vert, horiz = a.split('_')
            if (vert, horiz) in seen:
                continue
            seen.add((vert, horiz))
            style = ParagraphStyle(
                name=f'_imgmk_{vert}_{horiz}', parent=self.styles['Small'],
                fontName=font_b, fontSize=8, alignment=align_map.get(horiz, 1),
                textColor=colors.HexColor(fg),
            )
            (above if vert == 'TOP' else below).append(Paragraph(mark, style))
        return above, below

    def _row_mark_cell(self, level, suffix, header=False):
        """A leading per-row mark cell for marked tables."""
        font_b = f"{_t(self.theme, 'font_family')}-Bold"
        if header:
            txt, color = 'MARK', colors.white
        else:
            txt = _escape_xml(self.marking.portion_mark(level, suffix)) if self.marking else ''
            color = colors.HexColor(self._mark_fg(level) if level else '#64748B')
        return Paragraph(txt, ParagraphStyle(
            name='_rowmk', parent=self.styles['Small'],
            fontName=font_b, fontSize=7, textColor=color,
        ))

    def _compute_banner_level(self):
        """High-water mark across every effective portion mark in the document."""
        if not self.marking:
            return None
        marks = [getattr(self.engagement, 'default_classification_level', None)]
        for s in self.sections:
            lvl, _ = self.marking.resolve(
                getattr(s, 'classification_level', None),
                getattr(s, 'classification_suffix', None),
            )
            marks.append(lvl)
        for f in self.findings:
            marks.append(self._eff_mark(f)[0])
            for ev in (f.evidence or []):
                if getattr(ev, 'include_in_report', False):
                    marks.append(self._eff_mark_evidence(ev, f)[0])
        for tc in self.testcases:
            marks.append(self._eff_mark(tc)[0])
        for ca in self.cleanup_artifacts:
            marks.append(self._eff_mark(ca)[0])
        return self.marking.highest(marks)

    # ── Banner painter ────────────────────────────────────────────

    def _draw_banner(self, canvas, doc):
        """Paint the document banner (page header/footer). High-water level.

        IC/DoD + custom: centered filled strip top *and* bottom of every page.
        TLP: a centered filled chip in both the header and the footer.
        """
        if not self.marking or not self._banner_level:
            return
        b = self.marking.banner(self._banner_level)
        if not b:
            return
        text, bg, fg = b
        W, H = doc.pagesize
        font_b = f"{_t(self.theme, 'font_family')}-Bold"
        canvas.saveState()
        if self.marking.banner_top_and_bottom:
            for y in (H - 16, 4):
                canvas.setFillColor(colors.HexColor(bg))
                canvas.rect(0, y, W, 14, fill=1, stroke=0)
                canvas.setFillColor(colors.HexColor(fg))
                canvas.setFont(font_b, 9)
                canvas.drawCentredString(W / 2.0, y + 3, text)
        else:
            # TLP: centered chip top + bottom (header + footer), at the page edges
            # so it clears the header zones and the footer page number.
            canvas.setFont(font_b, 9)
            tw = canvas.stringWidth(text, font_b, 9)
            cx = W / 2.0
            for y in (H - 18, 6):
                canvas.setFillColor(colors.HexColor(bg))
                canvas.rect(cx - tw / 2 - 6, y - 3, tw + 12, 14, fill=1, stroke=0)
                canvas.setFillColor(colors.HexColor(fg))
                canvas.drawCentredString(cx, y, text)
        canvas.restoreState()

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
        """Running header + footer: accent rule, L/C/R zones, banner, page no."""
        canvas.saveState()
        font     = _t(self.theme, 'font_family')
        font_b   = f'{font}-Bold'
        primary  = _t(self.theme, 'primary_color')
        muted    = _t(self.theme, 'muted_text_color')
        show_num = _t(self.theme, 'show_page_numbers')
        W, H     = doc.pagesize

        # ── Top accent rule ────────────────
        canvas.setStrokeColor(colors.HexColor(primary))
        canvas.setLineWidth(2)
        canvas.line(54, H - 38, W - 54, H - 38)

        # ── Header zones (fall back to legacy header_text / engagement name) ──
        h_left   = _t(self.theme, 'header_left') or _t(self.theme, 'header_text') or self.engagement.name
        h_center = _t(self.theme, 'header_center')
        h_right  = _t(self.theme, 'header_right')
        canvas.setFont(font_b, 8)
        canvas.setFillColor(colors.HexColor(muted))
        if h_left:
            canvas.drawString(54, H - 28, str(h_left)[:60])
        if h_center:
            canvas.drawCentredString(W / 2.0, H - 28, str(h_center)[:60])
        if h_right:
            canvas.drawRightString(W - 54, H - 28, str(h_right)[:60])

        # ── Footer rule + zones ────────────
        canvas.setStrokeColor(colors.HexColor('#E2E8F0'))
        canvas.setLineWidth(0.5)
        canvas.line(54, 36, W - 54, 36)

        # When marking is on, the classification lives in the banner, so the
        # legacy footer_text (default "CONFIDENTIAL") is suppressed to avoid a
        # second, conflicting marking.
        legacy_footer = None if (self.marking and self._banner_level) else _t(self.theme, 'footer_text')
        f_left   = _t(self.theme, 'footer_left') or legacy_footer
        f_center = _t(self.theme, 'footer_center')
        f_right  = _t(self.theme, 'footer_right')
        canvas.setFont(font, 8)
        canvas.setFillColor(colors.HexColor(muted))
        if f_left:
            canvas.drawString(54, 24, str(f_left)[:80])
        if f_center:
            canvas.drawCentredString(W / 2.0, 24, str(f_center)[:80])
        # Page number takes the right zone unless an explicit footer_right is set.
        # When "Page X of Y" is on, the counting canvas draws it instead.
        show_x_of_y = _t(self.theme, 'show_page_x_of_y')
        if f_right:
            canvas.drawRightString(W - 54, 24, str(f_right)[:80])
        elif show_num and not show_x_of_y:
            canvas.drawRightString(W - 54, 24, f'Page {doc.page}')

        canvas.restoreState()

        # Banner painted last so it sits cleanly above everything else.
        self._draw_banner(canvas, doc)

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

        template    = (_t(self.theme, 'cover_template') or 'banded')
        bg_img_data = _t(self.theme, 'cover_background_base64')

        # ── Background: full-bleed image (with scrim) or solid fill ──
        drew_image = False
        if bg_img_data:
            stream = _decode_logo(bg_img_data)
            if stream:
                try:
                    from reportlab.lib.utils import ImageReader
                    canvas.drawImage(ImageReader(stream), 0, 0, width=W, height=H,
                                     preserveAspectRatio=False, mask='auto')
                    drew_image = True
                except Exception:
                    pass
        if not drew_image:
            canvas.setFillColor(colors.HexColor(cover_bg))
            canvas.rect(0, 0, W, H, fill=1, stroke=0)
        else:
            # Dark scrim keeps the title legible over a photo.
            canvas.saveState()
            canvas.setFillColor(colors.HexColor('#0F172A'))
            canvas.setFillAlpha(0.55)
            canvas.rect(0, 0, W, H, fill=1, stroke=0)
            canvas.restoreState()

        # ── Geometric accents (banded only, and not over a photo) ──
        if template == 'banded' and not drew_image:
            canvas.setFillColor(colors.HexColor('#1E293B'))
            p = canvas.beginPath()
            p.moveTo(W * 0.55, H); p.lineTo(W, H); p.lineTo(W, H * 0.60); p.close()
            canvas.drawPath(p, fill=1, stroke=0)
            canvas.setFillColor(colors.HexColor(primary))
            p2 = canvas.beginPath()
            p2.moveTo(W * 0.68, H); p2.lineTo(W * 0.72, H); p2.lineTo(W, H * 0.72); p2.lineTo(W, H * 0.68); p2.close()
            canvas.drawPath(p2, fill=1, stroke=0)

        # ── Bottom band (banded / classified) ─────────────────────
        draw_bottom_band = template in ('banded', 'classified')
        if draw_bottom_band:
            canvas.setFillColor(colors.HexColor(primary))
            canvas.rect(0, 0, W, 6, fill=1, stroke=0)
            canvas.setFillColor(colors.HexColor('#1E293B'))
            canvas.rect(0, 6, W, 52, fill=1, stroke=0)
        # 'classified' adds a matching top band to frame the marking banner.
        if template == 'classified':
            canvas.setFillColor(colors.HexColor('#1E293B'))
            canvas.rect(0, H - 40, W, 40, fill=1, stroke=0)

        # Classification label — suppressed when marking is on (the banner
        # carries the classification, and is painted over the cover separately).
        band_y = 26 if draw_bottom_band else 30
        if not (self.marking and self._banner_level):
            canvas.setFillColor(colors.HexColor(primary))
            canvas.setFont(font_b, 8)
            _t_classify = _t(self.theme, 'footer_text') or 'CONFIDENTIAL'
            canvas.drawCentredString(W / 2, band_y, f'● {_t_classify.upper()} ●')

        # Date
        canvas.setFillColor(colors.HexColor('#94A3B8'))
        canvas.setFont(font, 8)
        canvas.drawRightString(W - 54, band_y, datetime.now().strftime('%B %d, %Y'))

        # ── Red accent rule (all templates except full-bleed image) ──
        if template != 'full_bleed_image':
            accent_y = H * 0.45
            canvas.setStrokeColor(colors.HexColor(primary))
            canvas.setLineWidth(2)
            canvas.line(54, accent_y, W * 0.5, accent_y)

        # ── Logo ───────────────────────────────────────────────────
        logo_data = _t(self.theme, 'logo_base64')
        # Fixed TOP edge for the logo; it grows downward as it scales so a large
        # logo never overlaps the top banner.
        logo_top_edge = H * 0.88
        if logo_data:
            logo_stream = _decode_logo(logo_data)
            if logo_stream:
                try:
                    from reportlab.lib.utils import ImageReader
                    from reportlab.platypus import Image as RLImage
                    ir = ImageReader(logo_stream)
                    iw, ih = ir.getSize()
                    # Preserve aspect ratio: bind to a base height, scaled by the
                    # theme's logo_scale percent; cap width so it can't overrun.
                    scale = (_t(self.theme, 'logo_scale') or 100) / 100.0
                    base_h = 1.0 * inch
                    target_h = base_h * scale
                    target_w = target_h * (iw / ih) if ih else 2.0 * inch
                    max_w = 4.0 * inch
                    if target_w > max_w:
                        target_w = max_w
                        target_h = target_w * (ih / iw) if iw else target_h
                    logo_stream.seek(0)
                    img = RLImage(logo_stream, width=target_w, height=target_h)
                    # Anchor top-left: drawOn's y is the bottom edge, so subtract
                    # the height to keep the top fixed.
                    img.drawOn(canvas, 54, logo_top_edge - target_h)
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

        # ── Cover metadata (subtitle / reference / version) ─────────
        cover_subtitle = _t(self.theme, 'cover_subtitle')
        if cover_subtitle:
            canvas.setFillColor(colors.HexColor('#94A3B8'))
            canvas.setFont(font, 11)
            canvas.drawString(54, H * 0.53, str(cover_subtitle)[:80])

        meta_bits = []
        ref = _t(self.theme, 'report_reference')
        ver = _t(self.theme, 'report_version')
        if ref:
            meta_bits.append(f'REF: {ref}')
        if ver:
            meta_bits.append(f'VERSION: {ver}')
        if meta_bits:
            canvas.setFillColor(colors.HexColor('#64748B'))
            canvas.setFont(font, 9)
            canvas.drawString(54, H * 0.28, '   |   '.join(str(b) for b in meta_bits))

        # ── Classification legend + distribution statement ──────────
        if self.marking and self._banner_level:
            self._draw_cover_marking(canvas, doc, font, font_b)

        canvas.restoreState()

    def _draw_cover_marking(self, canvas, doc, font, font_b):
        """Classification legend (one colored chip per level) and the
        distribution statement, drawn low on the cover above the bottom band."""
        W, H = doc.pagesize
        y = H * 0.20
        if self.marking.show_legend:
            canvas.setFillColor(colors.HexColor('#94A3B8'))
            canvas.setFont(font_b, 8)
            canvas.drawString(54, y + 16, 'CLASSIFICATION LEGEND')
            x = 54
            for abbr, full_name, bg, fg in self.marking.legend_entries():
                label = full_name or abbr
                canvas.setFont(font_b, 7)
                tw = canvas.stringWidth(label, font_b, 7)
                canvas.setFillColor(colors.HexColor(bg))
                canvas.rect(x, y, tw + 10, 12, fill=1, stroke=0)
                canvas.setFillColor(colors.HexColor(fg))
                canvas.drawString(x + 5, y + 3, label)
                x += tw + 18
                if x > W - 80:
                    break

        dist = self.marking.distribution_statement
        if dist:
            canvas.setFillColor(colors.HexColor('#64748B'))
            canvas.setFont(font, 7)
            # Wrap to ~95 chars/line, max 3 lines.
            words, line, lines = str(dist).split(), '', []
            for w in words:
                if len(line + ' ' + w) > 95:
                    lines.append(line.strip())
                    line = w
                else:
                    line += ' ' + w
            if line.strip():
                lines.append(line.strip())
            for i, ln in enumerate(lines[:3]):
                canvas.drawString(54, (H * 0.20) - 14 - (i * 9), ln)

    # ── Table of Contents ─────────────────────────────────────────

    def _render_toc(self, elements):
        font      = _t(self.theme, 'font_family')
        font_b    = f'{font}-Bold'
        body_c    = _t(self.theme, 'body_text_color')
        body_size = _t(self.theme, 'font_size_body')

        # Section title bar (excluded from the outline/TOC so it doesn't list itself)
        elements.append(self._section_header_table('TABLE OF CONTENTS', outline=False))
        elements.append(Spacer(1, 16))

        # Real TOC: entries + page numbers are filled in by the doc template's
        # afterFlowable notifications during multiBuild. Dot leaders + right-
        # aligned page numbers are drawn by the flowable itself.
        toc = TableOfContents()
        toc.dotsMinLevel = 0
        toc.levelStyles = [
            ParagraphStyle(
                name='TOCLevel0', parent=self.styles['TOCEntry'],
                fontName=font_b, fontSize=body_size, leading=body_size + 8,
                textColor=colors.HexColor(body_c),
                spaceBefore=4, firstLineIndent=0, leftIndent=0,
            ),
        ]
        self.toc = toc
        elements.append(toc)
        elements.append(PageBreak())

    # ── Section header helper ─────────────────────────────────────

    def _section_header_table(self, title: str, section=None, outline: bool = True) -> Table:
        """A full-width section heading.

        Marked with the section's explicit mark, else the static-heading mark
        (U by default). Dark color-block background is toggleable via the theme
        (`show_section_title_background`); off → a plain colored heading with an
        accent rule. Tagged for the PDF outline/TOC unless `outline=False`.
        """
        dark      = _t(self.theme, 'secondary_color')
        primary   = _t(self.theme, 'primary_color')
        show_bg   = _t(self.theme, 'show_section_title_background')
        show_bg   = True if show_bg is None else bool(show_bg)

        tok = self._heading_mark_token(section)
        prefix = f'{_escape_xml(tok)} ' if tok else ''
        cell_style = ParagraphStyle(
            name='_SectHdr', parent=self.styles['SectionTitle'],
            textColor=colors.white if show_bg else colors.HexColor(primary),
        )
        cell = Paragraph(f'{prefix}{_escape_xml(title)}', cell_style)
        t = Table([[cell]], colWidths=[6.5 * inch])
        style = [
            ('LEFTPADDING', (0, 0), (-1, -1), 14 if show_bg else 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 14),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ]
        if show_bg:
            style.append(('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(dark)))
        else:
            style.append(('LINEBELOW', (0, 0), (-1, -1), 1.5, colors.HexColor(primary)))
        t.setStyle(TableStyle(style))
        if outline:
            # TOC entry + PDF bookmark carry the mark too (e.g. "(U) Findings").
            t._outline_label = f'{tok} {title}' if tok else title
        return t

    # ── Severity chart ────────────────────────────────────────────

    def _severity_summary_table(self, severity_counts: dict) -> Table:
        """Horizontal mini-bar chart as a styled table."""
        font   = _t(self.theme, 'font_family')
        font_b = f'{font}-Bold'
        max_count = max((severity_counts.get(s, 0) for s in _SEV_ORDER), default=1) or 1
        bar_max_w = 180  # points

        rows = []
        for sev in _SEV_ORDER:
            hex_col = self._sev_hex(sev)
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
        sev_hex   = self._sev_hex(sev_str)
        sev_bg    = _SEV_BG_COLORS.get(sev_str, '#F8FAFC')
        font      = _t(self.theme, 'font_family')
        font_b    = f'{font}-Bold'
        body_c    = _t(self.theme, 'body_text_color')
        muted_c   = _t(self.theme, 'muted_text_color')
        dark      = _t(self.theme, 'secondary_color')

        show_bar = _t(self.theme, 'show_finding_severity_bar')
        show_bar = True if show_bar is None else bool(show_bar)

        elements = []

        def _label_para(label):
            return Paragraph(label, ParagraphStyle(
                name=f'L_{label}_{idx}', parent=self.styles['Label'],
                fontName=font_b, fontSize=8,
                textColor=colors.HexColor(muted_c),
            ))

        # -- Header row: number + title (severity now lives in the meta row)
        title_text = Paragraph(
            f'<font color="{sev_hex}">F{idx:02d}</font>  '
            f'{self._mark_prefix(finding)}{_escape_xml(finding.title)}',
            ParagraphStyle(
                name=f'FT_{idx}', parent=self.styles['FindingTitle'],
                textColor=colors.white, fontSize=11, fontName=font_b, leading=15,
            )
        )
        header_t = Table([[title_text]], colWidths=[6.5 * inch])
        header_t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(dark)),
            ('LEFTPADDING', (0, 0), (-1, -1), 14),
            ('RIGHTPADDING', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 9),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(header_t)

        # -- Meta row: criticality + CVSS, split columns, first under title.
        meta_val_style = ParagraphStyle(
            name=f'MV_{idx}', parent=self.styles['BodyText2'],
            fontSize=10, fontName=font_b, textColor=colors.HexColor(body_c), spaceAfter=0,
        )
        cvss_text = ''
        if finding.cvss_score is not None:
            cvss_text = f'{finding.cvss_score}'
            if finding.cvss_vector:
                cvss_text += f'  |  {finding.cvss_vector}'
        meta_t = Table(
            [
                [_label_para('CRITICALITY'), _label_para('CVSS')],
                [Paragraph(f'<font color="{sev_hex}">{sev_str}</font>', meta_val_style),
                 Paragraph(_escape_xml(cvss_text) if cvss_text else '—', meta_val_style)],
            ],
            colWidths=[2.4 * inch, 4.1 * inch],
        )
        meta_t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(sev_bg)),
            ('LEFTPADDING', (0, 0), (-1, -1), 14),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LINEAFTER', (0, 0), (0, -1), 0.25, colors.HexColor('#E2E8F0')),
            ('LINEBELOW', (0, 0), (-1, -1), 0.25, colors.HexColor('#E2E8F0')),
        ]))
        elements.append(meta_t)

        # -- Body: details in a clean two-section layout
        body_rows = []

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

        # Inline images in the finding's markdown fields inherit the finding's
        # effective mark.
        _f_lvl, _f_suf = self._eff_mark(finding)
        _f_mark = self.marking.portion_mark(_f_lvl, _f_suf) if (self.marking and _f_lvl) else None
        _f_anchors = self.marking.image_anchors if self.marking else None

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
                mark_text=_f_mark, mark_anchors=_f_anchors, mark_fg=self._mark_fg(_f_lvl),
            )
            if not flowables:
                return
            body_rows.append([_label_para(label), flowables])

        asset_names = ', '.join([a.name for a in finding.assets]) if finding.assets else 'N/A'
        _add_row('AFFECTED ASSETS', asset_names)
        # (CVSS now shown in the meta row alongside criticality.)

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
            ]))
            elements.append(body_t)
        else:
            elements.append(Spacer(1, 8))

        card = Table([[e] for e in elements], colWidths=[6.5 * inch])
        card_style = [
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
        ]
        # Severity bar on the card's left edge, drawn AFTER the box so it sits
        # on top (no border overlap). Toggleable via the theme.
        if show_bar:
            card_style.append(('LINEBEFORE', (0, 0), (0, -1), 5, colors.HexColor(sev_hex)))
        card.setStyle(TableStyle(card_style))
        return card

    # ── Generate ──────────────────────────────────────────────────

    def generate(self) -> bytes:
        buffer   = io.BytesIO()
        page_size = _get_page_size(_t(self.theme, 'page_size'))
        # Compute the document banner (high-water mark) once up front so the
        # per-page header/footer callback can paint it.
        self._banner_level = self._compute_banner_level()
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

        # Sections
        for section in self.sections:
            if getattr(section, 'page_break_before', False):
                elements.append(PageBreak())
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

    def _render_text_section(self, elements, section: ReportSection):
        elements.append(self._section_header_table(section.title.upper(), section))
        elements.append(Spacer(1, 14))
        if section.content:
            s_lvl, s_suf = self._eff_mark(section)
            s_mark = self.marking.portion_mark(s_lvl, s_suf) if (self.marking and s_lvl) else None
            for fl in _md_to_flowables(
                section.content, self.styles['BodyText2'],
                image_resolver=self._resolve_markdown_image,
                mark_text=s_mark,
                mark_anchors=self.marking.image_anchors if self.marking else None,
                mark_fg=self._mark_fg(s_lvl),
            ):
                elements.append(fl)
        elements.append(Spacer(1, 20))

    def _render_findings_section(self, elements, section: ReportSection):
        elements.append(self._section_header_table(section.title.upper(), section))
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

        elements.append(Paragraph(f"{self._heading_mark_prefix()}Severity Distribution", self.styles['SubSectionTitle']))
        # The aggregate chart carries the engagement-default mark.
        sev_mark = self.marking.resolve(None, None) if self.marking else (None, None)
        sev_above, sev_below = self._table_mark_flowables([sev_mark])
        for fl in sev_above:
            elements.append(fl)
        elements.append(self._severity_summary_table(severity_counts))
        for fl in sev_below:
            elements.append(fl)
        elements.append(Spacer(1, 24))

        # ── Finding details ────────────────────────────────────────
        elements.append(Paragraph(f"{self._heading_mark_prefix()}Detailed Findings", self.styles['SubSectionTitle']))
        elements.append(Spacer(1, 8))

        for idx, finding in enumerate(self.findings, 1):
            card = self._finding_card(idx, finding)
            # Each finding card is its own table → mark per the table guide.
            above, below = self._table_mark_flowables([self._eff_mark(finding)])
            elements.append(KeepTogether(above + [card] + below))
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

        # Image mark placement policy (per the marking profile).
        anchors = self.marking.image_anchors if self.marking else []
        overlay_anchors = [a for a in anchors if a != 'CAPTION']
        show_filenames = _t(self.theme, 'show_evidence_filenames')

        for ev in evidence_list:
            mime = (ev.mime_type or '').lower()

            # Effective mark for this evidence item (inherits the finding).
            ev_lvl, ev_suf = self._eff_mark_evidence(ev, finding)
            ev_mark_raw = self.marking.portion_mark(ev_lvl, ev_suf) if self.marking else ''
            ev_mark_esc = _escape_xml(ev_mark_raw)

            # Build caption (filename optional; mark-prefixed when CAPTION anchor).
            caption_parts = []
            if ev.description:
                caption_parts.append(ev.description)
            if show_filenames:
                caption_parts.append(f'[{ev.original_filename}]')
            caption_text = _escape_xml('  '.join(caption_parts))
            if ev_mark_esc and 'CAPTION' in anchors:
                caption_text = f'{ev_mark_esc}  {caption_text}'.strip()

            if mime in self._IMAGE_MIMES and self.storage:
                file_bytes = self._fetch_file_bytes(ev.filename)
                if file_bytes:
                    try:
                        img_stream = io.BytesIO(file_bytes)
                        # Default: marks sit OUTSIDE the image (strips above/below)
                        # so they never overlap content. stamp_images additionally
                        # burns the mark onto the bitmap (detached-screenshot safety).
                        do_stamp = bool(self.marking and self.marking.stamp_images and ev_mark_raw)
                        stamp_anchors = overlay_anchors or (['TOP_LEFT'] if do_stamp else [])
                        if do_stamp and stamp_anchors:
                            img = MarkedImage(img_stream, mark_text=ev_mark_raw,
                                              anchors=stamp_anchors, mark_fg=self._mark_fg(ev_lvl))
                        else:
                            img = Image(img_stream)
                        iw, ih = img.imageWidth, img.imageHeight
                        if iw and ih:
                            scale = min(page_w / iw, max_img_h / ih, 1.0)
                            img.drawWidth  = iw * scale
                            img.drawHeight = ih * scale
                        img.hAlign = 'CENTER'
                        above_lines, below_lines = self._anchor_mark_lines(ev_mark_raw, overlay_anchors, self._mark_fg(ev_lvl))
                        block = above_lines + [img] + below_lines
                        if caption_text:
                            block.append(Paragraph(caption_text, ParagraphStyle(
                                name=f'ImgCap_{ev.id}', parent=self.styles['Caption'],
                                alignment=1, spaceAfter=6,
                            )))
                        elements.append(KeepTogether(block))
                        elements.append(Spacer(1, 4))
                        continue
                    except Exception as exc:
                        _log.warning(f'Could not embed image {ev.filename!r}: {exc}')

            # Non-image or failed image → text attachment reference. Always carry
            # the mark (an attachment has no figure to stamp).
            attach_caption = f'{ev_mark_esc}  {caption_text}' if (ev_mark_esc and 'CAPTION' not in anchors) else caption_text
            elements.append(Paragraph(
                f'\U0001f4ce  {attach_caption}',
                ParagraphStyle(
                    name=f'AttachRef_{ev.id}', parent=self.styles['BodyText2'],
                    fontSize=9, textColor=colors.HexColor(muted), spaceAfter=4,
                    alignment=1,
                ),
            ))

    # ── Table section renderers ───────────────────────────────────

    def _render_testcases_section(self, elements, section: ReportSection):
        elements.append(self._section_header_table(section.title.upper(), section))
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

        per_row = bool(self.marking and self.marking.per_row)
        zebra, alt_bg, grid = self._table_style_tokens()

        header_cells = [
            Paragraph('TEST CASE', header_style),
            Paragraph('CATEGORY', header_style),
            Paragraph('EXECUTED', header_style),
            Paragraph('RESULT', header_style),
        ]
        if per_row:
            header_cells = [self._row_mark_cell(None, None, header=True)] + header_cells
        rows = [header_cells]

        tc_levels = []
        for tc in self.testcases:
            lvl, suf = self._eff_mark(tc)
            tc_levels.append((lvl, suf))
            executed = '✓' if tc.is_executed else '–'
            result   = '✓ Pass' if tc.is_successful else ('✗ Fail' if tc.is_successful is False else 'N/A')
            cells = [
                Paragraph(_escape_xml(tc.title[:80]), cell_style),
                Paragraph(_v(tc.category).replace('_', ' ').title(), cell_style),
                Paragraph(executed, cell_style),
                Paragraph(result, cell_style),
            ]
            if per_row:
                cells = [self._row_mark_cell(lvl, suf)] + cells
            rows.append(cells)

        if per_row:
            col_widths = [0.55 * inch, 2.45 * inch, 1.4 * inch, 0.85 * inch, 1.0 * inch]
            center_from = 3
        else:
            col_widths = [3.0 * inch, 1.4 * inch, 0.85 * inch, 1.0 * inch]
            center_from = 2

        t = Table(rows, colWidths=col_widths, repeatRows=1)
        style = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(dark)),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (center_from, 1), (-1, -1), 'CENTER'),
            ('TOPPADDING', (0, 0), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('LINEBELOW', (0, 0), (-1, -1), 0.25, grid),
        ]
        if zebra:
            style.append(('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, alt_bg]))
        t.setStyle(TableStyle(style))

        above, below = self._table_mark_flowables(tc_levels)
        for fl in above:
            elements.append(fl)
        elements.append(t)
        for fl in below:
            elements.append(fl)
        elements.append(Spacer(1, 20))

    def _render_cleanup_artifacts_section(self, elements, section: ReportSection):
        elements.append(self._section_header_table(section.title.upper(), section))
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

        per_row = bool(self.marking and self.marking.per_row)
        zebra, alt_bg, grid = self._table_style_tokens()

        header_cells = [
            Paragraph('ARTIFACT', header_style),
            Paragraph('TYPE', header_style),
            Paragraph('STATUS', header_style),
            Paragraph('LOCATION', header_style),
        ]
        if per_row:
            header_cells = [self._row_mark_cell(None, None, header=True)] + header_cells
        rows = [header_cells]

        ca_levels = []
        for ca in self.cleanup_artifacts:
            lvl, suf = self._eff_mark(ca)
            ca_levels.append((lvl, suf))
            cells = [
                Paragraph(_escape_xml(ca.title[:60]), cell_style),
                Paragraph(_v(ca.artifact_type).replace('_', ' ').title(), cell_style),
                Paragraph(_v(ca.status).replace('_', ' ').title(), cell_style),
                Paragraph(_escape_xml((ca.location or 'N/A')[:50]), cell_style),
            ]
            if per_row:
                cells = [self._row_mark_cell(lvl, suf)] + cells
            rows.append(cells)

        if per_row:
            col_widths = [0.55 * inch, 1.95 * inch, 1.2 * inch, 1.15 * inch, 1.65 * inch]
        else:
            col_widths = [2.3 * inch, 1.3 * inch, 1.2 * inch, 1.7 * inch]

        t = Table(rows, colWidths=col_widths, repeatRows=1)
        style = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(dark)),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('LINEBELOW', (0, 0), (-1, -1), 0.25, grid),
        ]
        if zebra:
            style.append(('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, alt_bg]))
        t.setStyle(TableStyle(style))

        above, below = self._table_mark_flowables(ca_levels)
        for fl in above:
            elements.append(fl)
        elements.append(t)
        for fl in below:
            elements.append(fl)

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
                _ca_lvl, _ca_suf = self._eff_mark(ca)
                _ca_mark = self.marking.portion_mark(_ca_lvl, _ca_suf) if (self.marking and _ca_lvl) else None
                flowables = _md_to_flowables(
                    str(val), cell_style, max_chars=max_chars,
                    image_resolver=self._resolve_markdown_image,
                    max_image_width=4.5 * inch, max_image_height=3.0 * inch,
                    mark_text=_ca_mark,
                    mark_anchors=self.marking.image_anchors if self.marking else None,
                    mark_fg=self._mark_fg(_ca_lvl),
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
                    [[Paragraph(f'{idx}. {self._mark_prefix(ca)}{_escape_xml(ca.title)}', ParagraphStyle(
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
                # Each cleanup entry is its own table → mark per the table guide.
                ca_above, ca_below = self._table_mark_flowables([self._eff_mark(ca)])
                elements.append(KeepTogether(ca_above + [header, body_t] + ca_below))
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


# ═══════════════════════════════════════════════════════════════════
# HTML Report Generator — self-contained, styled, marking-aware
# ═══════════════════════════════════════════════════════════════════

class HTMLReportGenerator:
    """Produces a single self-contained HTML document (inline CSS, base64
    images) — an editable deliverable clients can open in a browser or import
    into Word. Honors the theme palette and the marking profile (banner +
    portion marks)."""

    def __init__(self, engagement, sections, findings, testcases,
                 cleanup_artifacts=None, theme=None, storage=None,
                 markdown_image_map=None, marking_profile=None):
        self.engagement = engagement
        self.sections = sections
        self.findings = sorted(findings, key=lambda x: _severity_rank(x.severity), reverse=True)
        self.testcases = testcases
        self.cleanup_artifacts = cleanup_artifacts or []
        self.theme = theme
        self.storage = storage
        self.markdown_image_map = markdown_image_map or {}
        self.marking = MarkingEngine(marking_profile, engagement) if marking_profile else None
        self._banner_level = self._compute_banner_level()

    # ── marking helpers ───────────────────────────────────────────
    def _eff(self, entity):
        if not self.marking:
            return (None, None)
        return self.marking.resolve(getattr(entity, 'classification_level', None),
                                    getattr(entity, 'classification_suffix', None))

    def _eff_evidence(self, ev, finding):
        if not self.marking:
            return (None, None)
        if getattr(ev, 'classification_level', None):
            return self.marking.resolve(ev.classification_level, ev.classification_suffix)
        return self._eff(finding)

    def _mark_prefix(self, entity):
        if not self.marking:
            return ''
        lvl, suf = self._eff(entity)
        tok = self.marking.portion_mark(lvl, suf)
        return f'<span class="pmark">{_escape_xml(tok)}</span> ' if tok else ''

    def _heading_mark_prefix(self, section=None):
        """Static-heading mark (lowest level by default) for structural headings,
        unless the section is explicitly marked."""
        if not self.marking:
            return ''
        if section is not None and getattr(section, 'classification_level', None):
            lvl, suf = self.marking.resolve(section.classification_level, section.classification_suffix)
        elif self.marking.static_heading_mode == 'INHERIT':
            lvl, suf = self.marking.resolve(None, None)
        else:
            lvl, suf = self.marking.lowest_level(), None
        tok = self.marking.portion_mark(lvl, suf)
        return f'<span class="pmark">{_escape_xml(tok)}</span> ' if tok else ''

    def _compute_banner_level(self):
        if not self.marking:
            return None
        marks = [getattr(self.engagement, 'default_classification_level', None)]
        for s in self.sections:
            marks.append(self.marking.resolve(getattr(s, 'classification_level', None),
                                              getattr(s, 'classification_suffix', None))[0])
        for f in self.findings:
            marks.append(self._eff(f)[0])
            for ev in (f.evidence or []):
                if getattr(ev, 'include_in_report', False):
                    marks.append(self._eff_evidence(ev, f)[0])
        for tc in self.testcases:
            marks.append(self._eff(tc)[0])
        for ca in self.cleanup_artifacts:
            marks.append(self._eff(ca)[0])
        return self.marking.highest(marks)

    def _sev_color(self, sev):
        key = _SEV_THEME_KEY.get((sev or '').upper())
        return (_t(self.theme, key) if key else None) or _SEV_COLORS.get((sev or '').upper(), '#64748B')

    # ── images ────────────────────────────────────────────────────
    def _data_uri(self, storage_key, content_type=None):
        if not self.storage or not storage_key:
            return None
        try:
            buf = io.BytesIO()
            self.storage.s3.download_fileobj(self.storage.bucket_name, storage_key, buf)
            b64 = base64.b64encode(buf.getvalue()).decode('ascii')
            return f'data:{content_type or "image/png"};base64,{b64}'
        except Exception as exc:
            _log.warning(f'HTML: could not embed image {storage_key!r}: {exc}')
            return None

    def _rewrite_inline_images(self, html_text):
        """Replace /markdown-images/<id> srcs with embedded data URIs."""
        if not self.markdown_image_map:
            return html_text

        def _repl(m):
            src = m.group(1)
            mm = re.search(r'/markdown-images/([^/?#"\']+)', src) or re.search(r'([0-9a-fA-F-]{16,})', src)
            if not mm:
                return m.group(0)
            image_id = mm.group(1).rsplit('.', 1)[0]
            info = self.markdown_image_map.get(image_id)
            if not info:
                return m.group(0)
            uri = self._data_uri(info.get('storage_key'), info.get('content_type'))
            return f'src="{uri}"' if uri else m.group(0)

        return re.sub(r'src="([^"]+)"', _repl, html_text)

    def _md(self, text):
        if not text:
            return ''
        import html as _html
        try:
            import markdown as _markdown
            # Report fields are markdown. Escape any raw HTML first so author
            # content (finding descriptions, etc.) cannot inject <script>/<img
            # onerror=…> into the rendered report — markdown syntax still works.
            safe = _html.escape(str(text), quote=False)
            html = _markdown.markdown(safe, extensions=['extra', 'sane_lists', 'nl2br'])
        except Exception:
            html = '<p>' + _escape_xml(str(text)).replace('\n', '<br/>') + '</p>'
        # Neutralize dangerous URL schemes markdown may emit from links like
        # [x](javascript:…). Our own embedded images (data: URIs) are added by
        # _rewrite_inline_images *after* this strip, so they are unaffected.
        html = re.sub(r'(?i)(href|src)\s*=\s*"\s*(?:javascript|vbscript|data):[^"]*"', r'\1="#"', html)
        return self._rewrite_inline_images(html)

    # ── generate ──────────────────────────────────────────────────
    def generate(self) -> str:
        primary = _t(self.theme, 'primary_color')
        dark = _t(self.theme, 'secondary_color')
        body_c = _t(self.theme, 'body_text_color')
        font = _t(self.theme, 'font_family')
        alt_bg = _t(self.theme, 'table_alt_row_bg')
        grid = _t(self.theme, 'table_grid_color')

        banner_html = ''
        if self.marking and self._banner_level:
            b = self.marking.banner(self._banner_level)
            if b:
                text, bg, fg = b
                banner_html = (f'<div class="banner" style="background:{bg};color:{fg}">'
                               f'{_escape_xml(text)}</div>')

        parts = [f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>{_escape_xml(_t(self.theme, 'cover_title') or 'Report')} — {_escape_xml(self.engagement.name)}</title>
<style>
  :root {{ --primary:{primary}; --dark:{dark}; --body:{body_c}; --alt:{alt_bg}; --grid:{grid}; }}
  body {{ font-family:{font}, Arial, sans-serif; color:var(--body); max-width:60rem; margin:0 auto; padding:2rem; line-height:1.5; }}
  .banner {{ text-align:center; font-weight:bold; padding:.4rem; letter-spacing:.05em; position:sticky; top:0; }}
  .banner.bottom {{ position:static; margin-top:2rem; }}
  h1.cover {{ color:var(--primary); font-size:2rem; margin:.2rem 0; }}
  .cover-meta {{ color:#64748b; font-size:.9rem; }}
  .section-bar {{ background:var(--dark); color:#fff; padding:.6rem 1rem; font-size:1.1rem; font-weight:bold; border-top:3px solid var(--primary); margin-top:2rem; }}
  table {{ border-collapse:collapse; width:100%; margin:1rem 0; font-size:.9rem; }}
  th {{ background:var(--dark); color:#fff; text-align:left; padding:.5rem; }}
  td {{ padding:.5rem; border-bottom:1px solid var(--grid); vertical-align:top; }}
  tr:nth-child(even) td {{ background:var(--alt); }}
  .finding {{ border:1px solid var(--grid); border-radius:6px; margin:1rem 0; overflow:hidden; }}
  .finding-head {{ background:var(--dark); color:#fff; padding:.6rem 1rem; font-weight:bold; }}
  .finding-body {{ padding:1rem; }}
  .label {{ color:#64748b; font-size:.7rem; font-weight:bold; text-transform:uppercase; letter-spacing:.05em; margin-top:.8rem; }}
  .sev {{ display:inline-block; padding:.1rem .5rem; border-radius:3px; color:#fff; font-size:.75rem; font-weight:bold; }}
  .pmark {{ font-weight:bold; color:var(--primary); }}
  .legend span {{ display:inline-block; padding:.1rem .5rem; margin:.1rem; border-radius:3px; font-size:.75rem; font-weight:bold; }}
  figure {{ margin:1rem 0; }} figure img {{ max-width:100%; border:1px solid var(--grid); }}
  figcaption {{ color:#64748b; font-size:.8rem; text-align:center; }}
  img {{ max-width:100%; }}
</style></head><body>"""]

        if banner_html:
            parts.append(banner_html)

        # Cover block
        parts.append('<header style="text-align:center;padding:2rem 0;border-bottom:2px solid var(--primary)">')
        parts.append(f'<h1 class="cover">{_escape_xml(_t(self.theme, "cover_title") or "Security Assessment Report")}</h1>')
        parts.append(f'<div class="cover-meta"><strong>{_escape_xml(self.engagement.name)}</strong></div>')
        parts.append(f'<div class="cover-meta">Client: {_escape_xml(self.engagement.client_name or "")}</div>')
        parts.append(f'<div class="cover-meta">{datetime.now().strftime("%B %d, %Y")}</div>')
        ref = _t(self.theme, 'report_reference'); ver = _t(self.theme, 'report_version')
        if ref or ver:
            parts.append(f'<div class="cover-meta">{_escape_xml(("REF: "+ref) if ref else "")} {_escape_xml(("v"+ver) if ver else "")}</div>')
        if self.marking and self.marking.show_legend and self._banner_level:
            chips = ''.join(
                f'<span style="background:{bg};color:{fg}">{_escape_xml(full or abbr)}</span>'
                for abbr, full, bg, fg in self.marking.legend_entries()
            )
            parts.append(f'<div class="legend" style="margin-top:1rem">{chips}</div>')
            if self.marking.distribution_statement:
                parts.append(f'<div class="cover-meta" style="margin-top:.5rem">{_escape_xml(self.marking.distribution_statement)}</div>')
        parts.append('</header>')

        for section in self.sections:
            st = section.section_type
            if st == SectionType.TEXT:
                parts.append(self._section_bar(section))
                parts.append(self._md(section.content or ''))
            elif st == SectionType.FINDINGS:
                parts.append(self._section_bar(section))
                parts.append(self._findings_html())
            elif st == SectionType.TESTCASES:
                parts.append(self._section_bar(section))
                parts.append(self._testcases_html())
            elif st == SectionType.CLEANUP_ARTIFACTS:
                parts.append(self._section_bar(section))
                parts.append(self._cleanup_html())

        if banner_html:
            parts.append(banner_html.replace('class="banner"', 'class="banner bottom"'))
        parts.append('</body></html>')
        return '\n'.join(parts)

    def _section_bar(self, section):
        return f'<div class="section-bar">{self._heading_mark_prefix(section)}{_escape_xml(section.title.upper())}</div>'

    def _findings_html(self):
        if not self.findings:
            return '<p>No findings recorded for this engagement.</p>'
        counts = {}
        for f in self.findings:
            k = _v(f.severity).upper()
            counts[k] = counts.get(k, 0) + 1
        rows = ''.join(
            f'<tr><td><span class="sev" style="background:{self._sev_color(s)}">{s}</span></td>'
            f'<td>{counts.get(s, 0)}</td></tr>'
            for s in _SEV_ORDER
        )
        out = [f'<h3>{self._heading_mark_prefix()}Severity Distribution</h3><table><tr><th>Severity</th><th>Count</th></tr>{rows}</table>']
        for idx, f in enumerate(self.findings, 1):
            sev = _v(f.severity).upper()
            out.append('<div class="finding">')
            out.append(f'<div class="finding-head" style="border-left:5px solid {self._sev_color(sev)}">'
                       f'{self._mark_prefix(f)}F{idx:02d} — {_escape_xml(f.title)} '
                       f'<span class="sev" style="background:{self._sev_color(sev)};float:right">{sev}</span></div>')
            out.append('<div class="finding-body">')
            assets = ', '.join(a.name for a in f.assets) if f.assets else 'N/A'
            out.append(f'<div class="label">Affected Assets</div><div>{_escape_xml(assets)}</div>')
            if f.cvss_score is not None:
                cvss = f'{f.cvss_score}' + (f' | {_escape_xml(f.cvss_vector)}' if f.cvss_vector else '')
                out.append(f'<div class="label">CVSS</div><div>{cvss}</div>')
            for lbl, val in (('Description', f.description), ('Impact', f.impact),
                             ('Steps to Reproduce', f.steps_to_reproduce),
                             ('Recommendations', f.mitigations), ('References', f.references)):
                if val:
                    out.append(f'<div class="label">{lbl}</div>{self._md(val)}')
            # Evidence images
            for ev in (f.evidence or []):
                if not getattr(ev, 'include_in_report', False):
                    continue
                ev_lvl, ev_suf = self._eff_evidence(ev, f)
                tok = self.marking.portion_mark(ev_lvl, ev_suf) if self.marking else ''
                mime = (ev.mime_type or '').lower()
                cap = f'{_escape_xml(tok)+" " if tok else ""}{_escape_xml(ev.description or "")} [{_escape_xml(ev.original_filename)}]'
                if mime in PDFReportGenerator._IMAGE_MIMES:
                    uri = self._data_uri(ev.filename, ev.mime_type)
                    if uri:
                        out.append(f'<figure><img src="{uri}" alt=""><figcaption>{cap}</figcaption></figure>')
                        continue
                out.append(f'<div class="cover-meta">📎 {cap}</div>')
            out.append('</div></div>')
        return '\n'.join(out)

    def _testcases_html(self):
        if not self.testcases:
            return '<p>No test cases recorded.</p>'
        per_row = bool(self.marking and self.marking.per_row)
        head = '<tr>' + ('<th>Mark</th>' if per_row else '') + '<th>Test Case</th><th>Category</th><th>Executed</th><th>Result</th></tr>'
        rows = []
        for tc in self.testcases:
            executed = '✓' if tc.is_executed else '–'
            result = '✓ Pass' if tc.is_successful else ('✗ Fail' if tc.is_successful is False else 'N/A')
            mark = ''
            if per_row:
                lvl, suf = self._eff(tc)
                mark = f'<td class="pmark">{_escape_xml(self.marking.portion_mark(lvl, suf))}</td>'
            rows.append(f'<tr>{mark}<td>{_escape_xml(tc.title)}</td><td>{_escape_xml(_v(tc.category).replace("_"," ").title())}</td>'
                        f'<td>{executed}</td><td>{result}</td></tr>')
        return f'<table>{head}{"".join(rows)}</table>'

    def _cleanup_html(self):
        if not self.cleanup_artifacts:
            return '<p>No cleanup artifacts recorded.</p>'
        per_row = bool(self.marking and self.marking.per_row)
        head = '<tr>' + ('<th>Mark</th>' if per_row else '') + '<th>Artifact</th><th>Type</th><th>Status</th><th>Location</th></tr>'
        rows = []
        for ca in self.cleanup_artifacts:
            mark = ''
            if per_row:
                lvl, suf = self._eff(ca)
                mark = f'<td class="pmark">{_escape_xml(self.marking.portion_mark(lvl, suf))}</td>'
            rows.append(f'<tr>{mark}<td>{_escape_xml(ca.title)}</td><td>{_escape_xml(_v(ca.artifact_type).replace("_"," ").title())}</td>'
                        f'<td>{_escape_xml(_v(ca.status).replace("_"," ").title())}</td><td>{_escape_xml(ca.location or "N/A")}</td></tr>')
        return f'<table>{head}{"".join(rows)}</table>'
