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
from models.finding import Finding
from models.testcase import TestCase
from models.cleanup_artifact import CleanupArtifact
from models.report_layout import ReportSection, SectionType
from models.report_theme import ReportTheme
from utils.marking import MarkedImage
from utils.report_content import (  # noqa: F401 — helpers re-exported for callers/tests
    NO_MARK, Mark, SEVERITY_ORDER, ReportDocument, build_report_document,
    _format_report_cf_value, _report_cf_rows, _score_info, _score_label,
    TESTCASE_STATUS_LABELS, _severity_rank, _title_case, _v, testcase_status,
)
from typing import List, Optional
import re
from html import unescape as _html_unescape


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
_SEV_ORDER = SEVERITY_ORDER

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


# ── Attack-chain (ChainLink) resolution ───────────────────────────────
#
# Operator-authored directed "led_to" edges over testcases / findings /
# vault items (backend/models/chain_link.py). This mirrors the resolution
# in routers/attack_graph.get_attack_graph so the report's attack paths
# reflect the operator's causal chain when one exists, falling back to the
# association-derived subgraph when a finding has no chain edges.
#
# `chain_edges` is a list of plain dicts (decoupled from the ORM/session):
#   {source_type, source_id, target_type, target_id, note}
# where *_type ∈ {testcase, finding, vault_item}.
#
# `tc_id_map` / `finding_id_map` map a raw entity id to the id that entity's
# node carries in the report graph (identity for the PDF, the F##/T# display
# id for the interactive HTML). `vault_items` maps a raw vault id to
# {name, item_type} for the vault items that participate in a chain — vault
# items are not otherwise in the report, so we surface only those.
#
# Returns (vault_nodes, resolved_edges, dupe_pairs):
#   vault_nodes  – [{'id':'vault-<id>','type':'vault','label','itype'}]
#   resolved_edges – [{'s','t','kind':'chain','note'}] (both endpoints resolved)
#   dupe_pairs   – set of (s,t) so callers can drop a factual 'discovered'
#                  edge duplicated by a same-direction chain edge.
def _resolve_chain_edges(chain_edges, tc_id_map, finding_id_map, vault_items):
    vault_items = vault_items or {}
    vault_ok = set(vault_items.keys())

    def _map(etype, eid):
        if etype == 'testcase':
            return tc_id_map.get(eid)
        if etype == 'finding':
            return finding_id_map.get(eid)
        if etype == 'vault_item':
            return ('vault-' + eid) if eid in vault_ok else None
        return None

    resolved = []
    used_vault = set()
    for e in (chain_edges or []):
        try:
            s = _map(e['source_type'], e['source_id'])
            t = _map(e['target_type'], e['target_id'])
        except (KeyError, TypeError):
            continue
        # Skip dangling edges whose endpoints no longer resolve to a rendered
        # node (deleted entity, filtered-out finding, unloaded vault item).
        if s is None or t is None or s == t:
            continue
        resolved.append({'s': s, 't': t, 'kind': 'chain', 'note': e.get('note') or None})
        if e['source_type'] == 'vault_item':
            used_vault.add(e['source_id'])
        if e['target_type'] == 'vault_item':
            used_vault.add(e['target_id'])

    vault_nodes = []
    for vid in used_vault:
        vi = vault_items.get(vid) or {}
        vault_nodes.append({
            'id': 'vault-' + vid, 'type': 'vault',
            'label': vi.get('name') or 'Vault item',
            'itype': vi.get('item_type') or '',
        })
    dupe_pairs = {(r['s'], r['t']) for r in resolved}
    return vault_nodes, resolved, dupe_pairs


def _chain_component(start_id, resolved_edges):
    """Connected component (chain edges treated as undirected) containing
    `start_id`. Returns a set of node ids, or None if `start_id` participates
    in no chain edge."""
    adj = {}
    for e in resolved_edges:
        adj.setdefault(e['s'], set()).add(e['t'])
        adj.setdefault(e['t'], set()).add(e['s'])
    if start_id not in adj:
        return None
    seen = {start_id}
    stack = [start_id]
    while stack:
        n = stack.pop()
        for m in adj.get(n, ()):
            if m not in seen:
                seen.add(m)
                stack.append(m)
    return seen


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



# Bold face of each base font a theme can pick. ReportLab's standard
# fonts don't follow one pattern ("Times-Roman" -> "Times-Bold"), so
# appending "-Bold" breaks for Times; an unknown name falls back to
# Helvetica rather than failing the whole PDF.
_BOLD_FONTS = {
    "Helvetica": "Helvetica-Bold", "Helvetica-Bold": "Helvetica-Bold",
    "Times-Roman": "Times-Bold", "Times-Bold": "Times-Bold",
    "Courier": "Courier-Bold", "Courier-Bold": "Courier-Bold",
}


def _bold_font(name: str | None) -> str:
    return _BOLD_FONTS.get(name or "Helvetica", "Helvetica-Bold")

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
    # Inline code first (so its contents aren't re-processed). Stash the emitted
    # <font> tag like every other construct above: without this, a subsequent
    # bold/italic pass can span-hop across the code span's contents (e.g. an
    # underscore inside `svc_backup2` pairing with another bare underscore
    # elsewhere), producing crossed tags that ReportLab's LIFO paraparser
    # rejects with "saw </i> instead of expected </font>".
    s = re.sub(r'`([^`]+)`', lambda m: _stash(f'<font name="Courier">{m.group(1)}</font>'), s)
    # Bold / italic / sub / sup. The character classes below exclude raw < and >
    # so an emphasis span can never straddle a tag this function already emitted
    # (bold before italic, etc.). Legitimate content has no raw angle brackets at
    # this point — Step 2 escaped them to &lt;/&gt; — so this only stops
    # span-hopping across emitted markup, never truncates real text.
    #
    # Backslash escapes (the editor saves a literal "_" or "*" as "\_" /
    # "\*") become literal characters, stashed so no emphasis pass sees them.
    s = re.sub(r'\\([!-/:-@\[-`{-~])', lambda m: _stash(m.group(1)), s)
    # Emphasis follows CommonMark flanking rules: the opening marker must be
    # followed, and the closing one preceded, by non-space, and "_" never
    # opens or closes inside a word, so identifiers (xp_cmdshell,
    # sp_configure) and arithmetic ("2 * 3 * 4") stay plain text.
    s = re.sub(r'\*\*(?![\s*])([^*<>]+?)(?<![\s*])\*\*', r'<b>\1</b>', s)
    s = re.sub(r'(?<![\w_])__(?![\s_])([^_<>]+?)(?<![\s_])__(?![\w_])', r'<b>\1</b>', s)
    # Italic (single * or _) — avoid eating bold markers we already replaced
    s = re.sub(r'(?<!\*)\*(?![\s*])([^*\n<>]+?)(?<![\s*])\*(?!\*)', r'<i>\1</i>', s)
    s = re.sub(r'(?<![\w_])_(?![\s_])([^_\n<>]+?)(?<![\s_])_(?![\w_])', r'<i>\1</i>', s)
    # Subscript ~text~ / superscript ^text^ (markdown shorthands; as in
    # pandoc, no whitespace inside, so "~/.ssh … ~/.bashrc" isn't one).
    s = re.sub(r'~([^~\s<>]+?)~', r'<sub>\1</sub>', s)
    s = re.sub(r'\^([^\^\s<>]+?)\^', r'<sup>\1</sup>', s)
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
        fontName=_bold_font(getattr(body_style, 'fontName', 'Helvetica')),
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
                fontName=_bold_font(getattr(body_style, 'fontName', 'Helvetica')),
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

    # ── Portion marking helpers ───────────────────────────────────

    def _mark_prefix(self, mark: Mark) -> str:
        """Escaped portion mark + trailing space, for prefixing a title/header."""
        return f'{_escape_xml(mark.token)} ' if mark.token else ''

    def _heading_mark_token(self, section=None) -> str:
        """Raw portion-mark token for a heading: an explicitly-marked section's
        own mark, else the structural-heading mark (U by default)."""
        return (section.heading_mark if section is not None else self.doc.structural_mark).token

    def _heading_mark_prefix(self, section=None) -> str:
        """Escaped mark prefix (+ trailing space) for a heading Paragraph."""
        tok = self._heading_mark_token(section)
        return f'{_escape_xml(tok)} ' if tok else ''

    def _md_flowables(self, text, style, mark: Mark, **kw):
        """Markdown → flowables, inline images marked with the portion's mark."""
        return _md_to_flowables(
            text, style, image_resolver=self._resolve_markdown_image,
            mark_text=mark.token or None,
            mark_anchors=self.marking.image_anchors if self.marking else None,
            mark_fg=mark.color, **kw)

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

        `marks` is a list of ``Mark`` (one per row/portion). The
        table-level mark is the highest-ranked portion, *carrying its suffix*
        (e.g. (S//SAR/TEST), not just (S))."""
        if not self.marking or not self.marking.table_anchors:
            return [], []
        best = self.doc.table_mark(marks)
        if not best:
            return [], []
        top = best.level
        mark = _escape_xml(best.token)
        font_b = _bold_font(_t(self.theme, 'font_family'))
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
        font_b = _bold_font(_t(self.theme, 'font_family'))
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

    def _row_mark_cell(self, mark: Mark = NO_MARK, header=False):
        """A leading per-row mark cell for marked tables."""
        font_b = _bold_font(_t(self.theme, 'font_family'))
        if header:
            txt, color = 'MARK', colors.white
        else:
            txt = _escape_xml(mark.token)
            color = colors.HexColor(mark.color if mark else '#64748B')
        return Paragraph(txt, ParagraphStyle(
            name='_rowmk', parent=self.styles['Small'],
            fontName=font_b, fontSize=7, textColor=color,
        ))

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
        font_b = _bold_font(_t(self.theme, 'font_family'))
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
        font_bold  = _bold_font(font)
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
        font_b   = _bold_font(font)
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
        font_b   = _bold_font(font)
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
        font_b    = _bold_font(font)
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
        font_b = _bold_font(font)
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

    # ── Overview / dashboard charts (reportlab.graphics, no new deps) ──

    def _severity_donut(self, counts, total, size=94):
        from reportlab.graphics.shapes import Drawing, Wedge, String, Circle
        d = Drawing(size, size)
        cx = cy = size / 2.0
        r = size / 2.0 - 3
        start = 90.0
        for sev in _SEV_ORDER:
            v = counts.get(sev, 0)
            if not v:
                continue
            ext = 360.0 * v / (total or 1)
            d.add(Wedge(cx, cy, r, start - ext, start, yradius=r,
                        fillColor=colors.HexColor(self._sev_hex(sev)),
                        strokeColor=colors.white, strokeWidth=1.4))
            start -= ext
        d.add(Circle(cx, cy, r * 0.60, fillColor=colors.white, strokeColor=None))
        d.add(String(cx, cy + 1, str(total), textAnchor='middle', fontSize=18,
                     fontName='Helvetica-Bold', fillColor=colors.HexColor(_t(self.theme, 'body_text_color'))))
        d.add(String(cx, cy - 12, 'FINDINGS', textAnchor='middle', fontSize=6,
                     fillColor=colors.HexColor(_t(self.theme, 'muted_text_color'))))
        return d

    def _metric_tiles(self, pairs):
        """pairs: (label, value, hexcolor) → compact 2-col grid of stat tiles."""
        muted = _t(self.theme, 'muted_text_color')
        cells = []
        for label, value, hexc in pairs:
            num = Paragraph(str(value), ParagraphStyle(
                name=f'_mn_{label}', parent=self.styles['Normal'], fontSize=17,
                fontName='Helvetica-Bold', textColor=colors.HexColor(hexc), leading=18))
            lbl = Paragraph(label, ParagraphStyle(
                name=f'_ml_{label}', parent=self.styles['Normal'], fontSize=7.5,
                textColor=colors.HexColor(muted), leading=9))
            inner = Table([[num], [lbl]], colWidths=[1.25 * inch])
            inner.setStyle(TableStyle([
                ('LEFTPADDING', (0, 0), (-1, -1), 10), ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (0, 0), 8), ('BOTTOMPADDING', (0, 0), (0, 0), 1),
                ('TOPPADDING', (0, 1), (0, 1), 0), ('BOTTOMPADDING', (0, 1), (0, 1), 8),
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
                ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
                ('LINEBEFORE', (0, 0), (0, -1), 2.5, colors.HexColor(hexc)),
            ]))
            cells.append(inner)
        grid = [[cells[i], cells[i + 1] if i + 1 < len(cells) else '']
                for i in range(0, len(cells), 2)]
        t = Table(grid, colWidths=[1.4 * inch, 1.4 * inch])
        t.setStyle(TableStyle([('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                               ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                               ('VALIGN', (0, 0), (-1, -1), 'TOP')]))
        return t

    def _exposure_chart(self, asset_rows, width=460, row_h=22):
        """asset_rows: (name, {sev:count}, total) → horizontal stacked bars."""
        from reportlab.graphics.shapes import Drawing, Rect, String
        rows = sorted(asset_rows, key=lambda x: -x[2])[:6]
        if not rows:
            return None
        maxt = max((r[2] for r in rows), default=1) or 1
        label_w = 150
        bar_max = width - label_w - 40
        h = len(rows) * row_h + 6
        d = Drawing(width, h)
        body = _t(self.theme, 'body_text_color'); muted = _t(self.theme, 'muted_text_color')
        for i, (name, sevs, total) in enumerate(rows):
            y = h - (i + 1) * row_h + 6
            nm = name if len(name) <= 30 else name[:29] + '…'
            d.add(String(0, y + 1, nm, fontSize=8, fillColor=colors.HexColor(body)))
            x = label_w
            for sev in _SEV_ORDER:
                c = sevs.get(sev, 0)
                if not c:
                    continue
                w = (c / maxt) * bar_max
                d.add(Rect(x, y - 1, w, 9, fillColor=colors.HexColor(self._sev_hex(sev)),
                           strokeColor=colors.white, strokeWidth=0.6))
                x += w
            d.add(String(x + 5, y + 1, str(total), fontSize=8, fontName='Helvetica-Bold',
                         fillColor=colors.HexColor(muted)))
        return d

    def _severity_legend(self, counts):
        """One-row colour key + per-severity counts (doubles as the donut legend)."""
        body = _t(self.theme, 'body_text_color')
        cells = []
        for sev in _SEV_ORDER:
            c = counts.get(sev, 0)
            cells.append(Paragraph(
                f'<font color="{self._sev_hex(sev)}">●</font> <b>{c}</b> {sev.capitalize()}',
                ParagraphStyle(name=f'_lg_{sev}', parent=self.styles['Normal'], fontSize=8.5,
                               textColor=colors.HexColor(body), leading=11)))
        t = Table([cells], colWidths=[1.3 * inch] * len(_SEV_ORDER))
        t.setStyle(TableStyle([
            ('TOPPADDING', (0, 0), (-1, -1), 7), ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
            ('LEFTPADDING', (0, 0), (-1, -1), 0), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LINEABOVE', (0, 0), (-1, 0), 0.5, colors.HexColor('#E2E8F0')),
            ('LINEBELOW', (0, 0), (-1, 0), 0.5, colors.HexColor('#E2E8F0')),
        ]))
        return t

    def _render_overview(self, elements):
        """A risk-overview dashboard page: rating + severity donut + key-metric
        tiles + exposure-by-asset — mirroring the interactive report overview."""
        if not self.findings:
            return
        counts = {k: v for k, v in self.doc.severity_counts.items() if v}
        total = len(self.findings)
        rating = self.doc.findings[0].severity
        # Only numeric models carry a real score; categorical ones store a
        # nominal sort key that must not be shown as e.g. "CVSS up to 9.5".
        numeric = [f for f in self.findings if _score_info(f)['score']]
        score = float(max(f.cvss_score for f in numeric)) if numeric else 0.0
        muted = _t(self.theme, 'muted_text_color')
        body = _t(self.theme, 'body_text_color')

        elements.append(self._section_header_table('RISK OVERVIEW', None))
        elements.append(Spacer(1, 14))

        rating_p = Paragraph(rating, ParagraphStyle(name='_rating', parent=self.styles['Normal'],
            fontSize=26, fontName='Helvetica-Bold', textColor=colors.HexColor(self._sev_hex(rating)), leading=27))
        score_line = (f'{_escape_xml(_score_label(numeric))} up to <b>{score:.1f}</b>'
                      if numeric else f'{len(self.findings)} findings rated')
        score_p = Paragraph(score_line, ParagraphStyle(name='_rscore',
            parent=self.styles['Normal'], fontSize=10, textColor=colors.HexColor(body), leading=13))
        cap_p = Paragraph('Overall risk posture', ParagraphStyle(name='_rcap', parent=self.styles['Normal'],
            fontSize=8, textColor=colors.HexColor(muted), leading=10))
        risk_cell = Table([[rating_p], [score_p], [cap_p]], colWidths=[2.0 * inch])
        risk_cell.setStyle(TableStyle([('LEFTPADDING', (0, 0), (-1, -1), 0),
                                       ('TOPPADDING', (0, 0), (-1, -1), 1), ('BOTTOMPADDING', (0, 0), (-1, -1), 1)]))

        agg = {}
        for f in self.findings:
            sev = _v(f.severity).upper()
            for a in (f.assets or []):
                d = agg.setdefault(a.name, {})
                d[sev] = d.get(sev, 0) + 1
        fixed = sum(1 for f in self.doc.findings if f.status_group == 'remediated')
        tiles = self._metric_tiles([
            ('FINDINGS', total, body),
            ('ASSETS', len(agg), '#3B82F6'),
            ('TEST CASES', len(self.testcases), '#059669'),
            ('FIXED', fixed, '#16A34A'),
        ])

        top = Table([[risk_cell, self._severity_donut(counts, total), tiles]],
                    colWidths=[2.1 * inch, 1.5 * inch, 2.9 * inch])
        top.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                                 ('LEFTPADDING', (0, 0), (-1, -1), 4), ('RIGHTPADDING', (0, 0), (-1, -1), 4),
                                 ('ALIGN', (1, 0), (1, 0), 'CENTER')]))
        elements.append(top)
        elements.append(Spacer(1, 16))
        elements.append(self._severity_legend(counts))
        elements.append(Spacer(1, 20))

        arows = [(name, sevs, sum(sevs.values())) for name, sevs in agg.items()]
        chart = self._exposure_chart(arows)
        if chart is not None:
            elements.append(Paragraph('EXPOSURE BY ASSET', ParagraphStyle(name='_exl', parent=self.styles['Label'],
                fontSize=8, fontName='Helvetica-Bold', textColor=colors.HexColor(muted), spaceAfter=8)))
            elements.append(chart)
        elements.append(PageBreak())

    # ── Finding card ──────────────────────────────────────────────

    def _finding_card(self, item) -> tuple:
        """Flowables for a single finding, as ``(head, body)``.

        ``head`` = the header + meta tables (kept together by the caller);
        ``body`` = the field flowables, rendered full-width so long content
        (e.g. an oversized code block) paginates instead of crashing.
        """
        finding   = item.src
        idx       = int(item.ref[1:])
        sev_str   = item.severity
        sev_hex   = self._sev_hex(sev_str)
        sev_bg    = _SEV_BG_COLORS.get(sev_str, '#F8FAFC')
        font      = _t(self.theme, 'font_family')
        font_b    = _bold_font(font)
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
            f'<font color="{sev_hex}">{item.ref}</font>  '
            f'{self._mark_prefix(item.mark)}{_escape_xml(item.title)}',
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

        # -- Meta row: criticality + score (labelled by its scoring model).
        meta_val_style = ParagraphStyle(
            name=f'MV_{idx}', parent=self.styles['BodyText2'],
            fontSize=10, fontName=font_b, textColor=colors.HexColor(body_c), spaceAfter=0,
        )
        score_info = item.score
        cvss_text = score_info['text']
        meta_t = Table(
            [
                [_label_para('CRITICALITY'), _label_para(_escape_xml(score_info['label'].upper()))],
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

        # -- Body: each field is a full-width, page-splittable block. Rendering
        # the body as top-level flowables (rather than nested table cells) lets
        # long content — e.g. a fenced code block taller than a page — paginate
        # instead of crashing ReportLab (a table row / KeepTogether can't be
        # split across a page boundary).
        body = []

        def _field_label(label):
            return Paragraph(label, ParagraphStyle(
                name=f'FL_{label}_{idx}', parent=self.styles['Label'],
                fontName=font_b, fontSize=8, leading=10,
                textColor=colors.HexColor(muted_c),
                spaceBefore=10, spaceAfter=3,
            ))

        def _add_row(label, value):
            """Plain (non-markdown) field — used for short scalar values."""
            if not value:
                return
            body.append(_field_label(label))
            body.append(Paragraph(_escape_xml(str(value)[:800]), ParagraphStyle(
                name=f'V_{label}_{idx}', parent=self.styles['BodyText2'],
                fontSize=9, textColor=colors.HexColor(body_c),
            )))

        def _add_md_row(label, value, max_chars=50000):
            """Markdown field — block-level markdown as top-level flowables."""
            if not value:
                return
            cell_body_style = ParagraphStyle(
                name=f'V_{label}_{idx}', parent=self.styles['BodyText2'],
                fontSize=9, textColor=colors.HexColor(body_c),
                spaceAfter=2,
            )
            # Inline images inherit the finding's effective mark.
            flowables = self._md_flowables(
                str(value), cell_body_style, item.mark, max_chars=max_chars,
                max_image_width=4.5 * inch, max_image_height=3.0 * inch,
            )
            if not flowables:
                return
            body.append(_field_label(label))
            body.extend(flowables)

        _add_row('AFFECTED ASSETS', ', '.join(a.name for a in item.assets) or 'N/A')
        # (The score is in the meta row alongside criticality.)

        for fld in item.fields:
            _add_md_row(fld.label.upper(), fld.markdown)

        # Admin-defined custom fields flagged show_in_report.
        for _cf_label, _cf_value in item.custom_fields:
            _add_row(_cf_label.upper(), _cf_value)

        # Attack path — the per-finding subgraph (test cases → finding → assets →
        # cleanup), mirroring the interactive report. Rendered only when there is
        # something beyond the finding node itself to show.
        if _t(self.theme, 'show_attack_graph') is not False:
            try:
                sg_nodes, sg_edges = self._finding_subgraph(finding)
                if len(sg_nodes) >= 2:
                    d = self._graph_drawing(sg_nodes, sg_edges, avail_w=6.4 * inch, compact=True)
                    if d is not None:
                        body.append(_field_label('ATTACK PATH'))
                        body.append(d)
            except Exception as _ge:
                _log.warning("attack-path graph render failed for finding %s: %s", finding.id, _ge)

        # `elements` holds the header + meta tables (small, page-safe) — the
        # "head" that should stay together; `body` holds the splittable field
        # flowables. Returned separately so the caller keeps the head together
        # while letting the body flow across pages.
        return elements, body

    # ── Attack graph (native reportlab.graphics; mirrors the web report) ──
    #
    # Same node/edge model as the interactive HTML report's graph:
    #   nodes: testcase | finding | asset | cleanup
    #   edges: subtest (parent→child TC) · discovered (TC→finding)
    #          · impacts (finding→asset) · cleanup (asset|finding→cleanup)
    # Rendered with a longest-path (Sugiyama-style) column layout, drawn once
    # per finding as an "attack path", and once for the whole engagement when
    # the graph is small enough to stay legible on a static page.

    _ENT_ASSET = '#2563EB'      # blue-600  (light-theme entity colors)
    _ENT_TESTCASE = '#059669'   # emerald-600
    _ENT_CLEANUP = '#4D7C0F'    # lime-700
    _ENT_VAULT = '#CA8A04'      # yellow-600 (vault items in a chain)

    def _resolved_chain(self):
        """(vault_nodes, resolved_edges, dupe_pairs) for this engagement's
        chain edges, resolved into the PDF graph's identity scheme (test cases
        and findings keep their raw entity id; vault items become 'vault-<id>').
        Cached; empty when there are no chain edges."""
        if not hasattr(self, '_rc_cache'):
            tc_map = {t.id: t.id for t in self.testcases}
            f_map = {f.id: f.id for f in self.findings}
            self._rc_cache = _resolve_chain_edges(
                self.chain_edges, tc_map, f_map, self.chain_vault_items)
        return self._rc_cache

    def _chain_subgraph_nodes(self, comp, resolved, vault_nodes):
        """Build (nodes, edges) for the chain connected-component `comp`."""
        dF, dT = self._display_ids()
        tcmap = {t.id: t for t in self.testcases}
        fmap = {f.id: f for f in self.findings}
        vmap = {v['id']: v for v in vault_nodes}
        nodes = []
        for nid in comp:
            if nid in tcmap:
                t = tcmap[nid]
                nodes.append({'id': t.id, 'type': 'testcase', 'label': t.title or 'Test case',
                              'did': dT.get(t.id, ''), 'status': self._graph_status(t)})
            elif nid in fmap:
                f = fmap[nid]
                nodes.append({'id': f.id, 'type': 'finding', 'label': f.title or 'Untitled',
                              'did': dF.get(f.id, ''), 'sev': _v(f.severity).upper()})
            elif nid in vmap:
                v = vmap[nid]
                nodes.append({'id': v['id'], 'type': 'vault', 'label': v['label'], 'did': ''})
        edges = [e for e in resolved if e['s'] in comp and e['t'] in comp]
        return nodes, edges

    @staticmethod
    def _graph_status(tc):
        st = testcase_status(tc)
        return None if st == 'none' else TESTCASE_STATUS_LABELS[st]

    def _display_ids(self):
        return ({f.id: f.ref for f in self.doc.findings},
                {t.id: t.ref for t in self.doc.testcases})

    def _node_color(self, n):
        t = n['type']
        if t == 'finding':
            return self._sev_hex(n.get('sev', 'INFO'))
        if t == 'testcase':
            return self._ENT_TESTCASE
        if t == 'asset':
            return self._ENT_ASSET
        if t == 'vault':
            return self._ENT_VAULT
        return self._ENT_CLEANUP

    def _edge_style(self, kind):
        """(hex, width, dash-or-None) — matches the web EDGE_STYLE mapping.

        'discovered' uses the web brand purple (not the PDF theme primary, which
        defaults to the same red as Critical severity and would read as a severity
        cue on an edge)."""
        return {
            'subtest':    ('#94A3B8', 1.0, None),
            'discovered': ('#7C3AED', 1.6, None),
            'impacts':    ('#60A5FA', 1.0, (3, 3)),
            'cleanup':    ('#B45309', 1.0, (2, 3)),
            # Operator-authored causal chain edge — indigo-400, matches the
            # app attack graph's CHAIN_EDGE_COLOR.
            'chain':      ('#818CF8', 2.0, None),
        }.get(kind, ('#94A3B8', 1.0, None))

    def _finding_subgraph(self, f):
        """(nodes, edges) for one finding.

        When the finding participates in operator-authored chain edges, the
        subgraph is the chain's connected component (test cases / findings /
        vault items reachable via ChainLink), drawn with the causal chain
        edges. Otherwise it falls back — unchanged — to the association-derived
        subgraph: the test cases that discovered it (with their parent chain),
        the finding, its assets, and its cleanup artifacts."""
        vault_nodes, resolved, _ = self._resolved_chain()
        if resolved:
            comp = _chain_component(f.id, resolved)
            if comp:
                return self._chain_subgraph_nodes(comp, resolved, vault_nodes)
        dF, dT = self._display_ids()
        tcmap = {t.id: t for t in self.testcases}
        nodes, edges, seen = [], [], set()
        for t in self.testcases:
            if any(x.id == f.id for x in (t.findings or [])):
                edges.append({'s': t.id, 't': f.id, 'kind': 'discovered'})
                cur = t
                while cur is not None:
                    if cur.id not in seen:
                        seen.add(cur.id)
                        nodes.append({'id': cur.id, 'type': 'testcase', 'label': cur.title or 'Test case',
                                      'did': dT.get(cur.id, ''), 'status': self._graph_status(cur)})
                    if cur.parent_id and cur.parent_id in tcmap:
                        edges.append({'s': cur.parent_id, 't': cur.id, 'kind': 'subtest'})
                        cur = tcmap[cur.parent_id]
                    else:
                        cur = None
        nodes.append({'id': f.id, 'type': 'finding', 'label': f.title or 'Untitled',
                      'did': dF.get(f.id, ''), 'sev': _v(f.severity).upper()})
        f_asset_names = {a.name for a in (f.assets or [])}
        seen_assets = set()
        for a in (f.assets or []):
            if a.name in seen_assets:
                continue
            seen_assets.add(a.name)
            nodes.append({'id': 'a-' + a.name, 'type': 'asset', 'label': a.name, 'did': ''})
            edges.append({'s': f.id, 't': 'a-' + a.name, 'kind': 'impacts'})
        for i, ca in enumerate(self.cleanup_artifacts):
            if any(x.id == f.id for x in (ca.findings or [])):
                cid = 'sC%d' % i
                nodes.append({'id': cid, 'type': 'cleanup', 'label': ca.title or 'Artifact', 'did': ''})
                linked_a = next((x.name for x in (ca.assets or [])), None)
                src = ('a-' + linked_a) if (linked_a and linked_a in f_asset_names) else f.id
                edges.append({'s': src, 't': cid, 'kind': 'cleanup'})
        return nodes, edges

    def _build_full_graph(self):
        """(nodes, edges) for the whole engagement — the web buildGraph()."""
        dF, dT = self._display_ids()
        nodes, edges, aid = [], [], {}
        for t in self.testcases:
            nodes.append({'id': t.id, 'type': 'testcase', 'label': t.title or 'Test case',
                          'did': dT.get(t.id, ''), 'status': self._graph_status(t)})
        for f in self.findings:
            nodes.append({'id': f.id, 'type': 'finding', 'label': f.title or 'Untitled',
                          'did': dF.get(f.id, ''), 'sev': _v(f.severity).upper()})
        asset_names = []
        for f in self.findings:
            for a in (f.assets or []):
                if a.name not in aid:
                    aid[a.name] = 'A%d' % len(asset_names)
                    asset_names.append(a.name)
        for name in asset_names:
            nodes.append({'id': aid[name], 'type': 'asset', 'label': name, 'did': ''})
        for i, ca in enumerate(self.cleanup_artifacts):
            cid = 'C%d' % i
            nodes.append({'id': cid, 'type': 'cleanup', 'label': ca.title or 'Artifact', 'did': ''})
            linked_a = next((x.name for x in (ca.assets or [])), None)
            linked_f = next((x.id for x in (ca.findings or [])), None)
            src = aid.get(linked_a) if (linked_a and linked_a in aid) else linked_f
            if src:
                edges.append({'s': src, 't': cid, 'kind': 'cleanup'})
        for t in self.testcases:
            if getattr(t, 'parent_id', None):
                edges.append({'s': t.parent_id, 't': t.id, 'kind': 'subtest'})
            for f in (t.findings or []):
                edges.append({'s': t.id, 't': f.id, 'kind': 'discovered'})
        for f in self.findings:
            for a in (f.assets or []):
                if a.name in aid:
                    edges.append({'s': f.id, 't': aid[a.name], 'kind': 'impacts'})
        # A filtered report (severity / status / …) keeps only the matching
        # findings, but test cases and cleanup artifacts still link to the
        # dropped ones: drop edges whose ends aren't drawn, or layering
        # raised KeyError and the PDF 500'd.
        drawn = {n['id'] for n in nodes}
        edges = [e for e in edges if e['s'] in drawn and e['t'] in drawn]
        # ── Chain overlay ──
        # Overlay operator-authored causal chain edges (and any vault items
        # they touch) onto the association-derived graph, mirroring the app's
        # attack graph. No chain edges → this is a no-op and the graph is
        # byte-identical to before.
        vault_nodes, resolved, dupes = self._resolved_chain()
        if resolved:
            existing_ids = {n['id'] for n in nodes}
            for v in vault_nodes:
                if v['id'] not in existing_ids:
                    nodes.append({'id': v['id'], 'type': 'vault', 'label': v['label'], 'did': ''})
                    existing_ids.add(v['id'])
            # Drop a factual 'discovered' edge duplicated by a same-direction
            # chain edge (same fact twice); a reverse-direction chain edge is a
            # distinct relationship and leaves 'discovered' intact.
            if dupes:
                edges = [e for e in edges
                         if not (e.get('kind') == 'discovered' and (e['s'], e['t']) in dupes)]
            for e in resolved:
                if e['s'] in existing_ids and e['t'] in existing_ids:
                    edges.append(e)
        return nodes, edges

    @staticmethod
    def _layer_nodes(nodes, edges):
        """Longest-path layering (the web renderGraph topo pass). Returns id→layer."""
        inD = {n['id']: 0 for n in nodes}
        outA = {n['id']: [] for n in nodes}
        for e in edges:
            if e['s'] not in outA or e['t'] not in inD:
                continue  # dangling edge: nothing to layer
            outA[e['s']].append(e['t'])
            inD[e['t']] += 1
        layer = {n['id']: 0 for n in nodes}
        ind = dict(inD)
        q = [nid for nid in inD if ind[nid] == 0]
        while q:
            nid = q.pop(0)
            for t in outA[nid]:
                if layer[nid] + 1 > layer[t]:
                    layer[t] = layer[nid] + 1
                ind[t] -= 1
                if ind[t] == 0:
                    q.append(t)
        return layer

    def _draw_node(self, group, n, NW, NH, compact):
        from reportlab.graphics.shapes import Rect, String, Circle
        col = self._node_color(n)
        x, y = n['x'], n['y']
        muted = _t(self.theme, 'muted_text_color')
        body = _t(self.theme, 'body_text_color')
        group.add(Rect(x, y, NW, NH, rx=4, ry=4, fillColor=colors.white,
                       strokeColor=colors.HexColor(col), strokeWidth=1.1))
        group.add(Rect(x, y, 3.2, NH, fillColor=colors.HexColor(col), strokeColor=None))
        group.add(Circle(x + 12, y + NH - 10, 3, fillColor=colors.HexColor(col), strokeColor=None))
        did = n.get('did', '')
        top = did
        if n['type'] == 'testcase' and n.get('status'):
            top = f'{did} · {n["status"]}' if did else n['status']
        if top:
            group.add(String(x + 20, y + NH - 12.5, top, fontSize=6.3, fontName='Helvetica-Bold',
                             fillColor=colors.HexColor(muted)))
        lim = 20 if compact else 24
        lbl = n['label'] if len(n['label']) <= lim else n['label'][:lim - 1] + '…'
        group.add(String(x + 8, y + 6, lbl, fontSize=7.4,
                         fillColor=colors.HexColor(body)))

    def _draw_edge(self, group, a, b, kind, NW, NH):
        from reportlab.graphics.shapes import Path
        hexc, w, dash = self._edge_style(kind)
        sx, sy = a['x'] + NW, a['y'] + NH / 2.0
        tx, ty = b['x'], b['y'] + NH / 2.0
        mx = (sx + tx) / 2.0
        p = Path(strokeColor=colors.HexColor(hexc), strokeWidth=w, fillColor=None)
        if dash:
            p.strokeDashArray = list(dash)
        p.moveTo(sx, sy)
        p.curveTo(mx, sy, mx, ty, tx, ty)
        group.add(p)

    def _graph_drawing(self, nodes, edges, avail_w, compact=True):
        from reportlab.graphics.shapes import Drawing, Group
        if not nodes:
            return None
        byId = {n['id']: n for n in nodes}
        edges = [e for e in edges if e['s'] in byId and e['t'] in byId]
        layer = self._layer_nodes(nodes, edges)
        NW = 118 if compact else 138
        NH = 30
        hgap, vgap = 32, 12
        cols = {}
        for n in nodes:
            cols.setdefault(layer[n['id']], []).append(n)
        max_layer = max(layer.values()) if layer else 0
        max_rows = max((len(v) for v in cols.values()), default=1)
        w_nat = (max_layer + 1) * NW + max_layer * hgap
        h_nat = max_rows * NH + (max_rows - 1) * vgap
        for L, ns in cols.items():
            col_h = len(ns) * NH + (len(ns) - 1) * vgap
            y0 = (h_nat - col_h) / 2.0
            for i, n in enumerate(ns):
                n['x'] = L * (NW + hgap)
                n['y'] = h_nat - y0 - NH - i * (NH + vgap)
        g = Group()
        for e in edges:
            self._draw_edge(g, byId[e['s']], byId[e['t']], e['kind'], NW, NH)
        for n in nodes:
            self._draw_node(g, n, NW, NH, compact)
        s = min(1.0, avail_w / w_nat) if w_nat > avail_w else 1.0
        if s != 1.0:
            g.transform = (s, 0, 0, s, 0, 0)
        d = Drawing(w_nat * s, h_nat * s)
        d.add(g)
        return d

    def _graph_legend(self):
        body = _t(self.theme, 'body_text_color')
        muted = _t(self.theme, 'muted_text_color')
        items = [(self._ENT_TESTCASE, 'Test case'), ('#64748B', 'Finding'),
                 (self._ENT_ASSET, 'Asset'), (self._ENT_CLEANUP, 'Cleanup')]
        cells = [Paragraph(f'<font color="{c}">■</font> {t}', ParagraphStyle(
                    name=f'_gl_{t}', parent=self.styles['Normal'], fontSize=8,
                    textColor=colors.HexColor(body), leading=10)) for c, t in items]
        edgep = Paragraph(
            'test&#8594;finding <b>discovered</b> · finding&#8943;asset <b>impacts</b> · &#8594;<b>cleanup</b>',
            ParagraphStyle(name='_gle', parent=self.styles['Normal'], fontSize=7.3,
                           textColor=colors.HexColor(muted), leading=10))
        t = Table([cells + [edgep]], colWidths=[0.9 * inch] * 4 + [2.9 * inch])
        t.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                               ('LEFTPADDING', (0, 0), (-1, -1), 0),
                               ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2)]))
        return t

    def _render_attack_graph_section(self, elements):
        """Full-engagement attack graph — only when small enough to read on paper.
        Larger engagements rely on the per-finding attack paths inside each card."""
        nodes, edges = self._build_full_graph()
        if len(nodes) < 3:
            return
        # Legibility gate: a static page can't pan/zoom, so a tall finding column
        # becomes an unreadable stripe. Skip past a threshold; per-finding paths cover it.
        layer = self._layer_nodes(nodes, edges)
        cols = {}
        for n in nodes:
            cols.setdefault(layer[n['id']], []).append(n['id'])
        # The width auto-scales to the page, so the tallest column (not the node
        # total) is what governs legibility on a static page. Past ~12 rows the
        # graph becomes a cramped stripe — skip it; the per-finding paths carry it.
        max_rows = max((len(v) for v in cols.values()), default=1)
        if max_rows > 12:
            return
        elements.append(PageBreak())
        elements.append(self._section_header_table('ATTACK GRAPH', None))
        elements.append(Spacer(1, 12))
        elements.append(self._graph_legend())
        elements.append(Spacer(1, 14))
        d = self._graph_drawing(nodes, edges, avail_w=6.5 * inch, compact=False)
        if d is not None:
            elements.append(d)
        elements.append(Spacer(1, 24))

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

    def _render_findings_section(self, elements, section):
        elements.append(self._section_header_table(section.title.upper(), section))
        elements.append(Spacer(1, 16))

        if not self.findings:
            elements.append(Paragraph('No findings recorded for this engagement.', self.styles['BodyText2']))
            elements.append(Spacer(1, 12))
            return

        # ── Severity overview ──────────────────────────────────────
        elements.append(Paragraph(f"{self._heading_mark_prefix()}Severity Distribution", self.styles['SubSectionTitle']))
        # The aggregate chart carries the engagement-default mark.
        sev_above, sev_below = self._table_mark_flowables([self.doc.default_mark])
        for fl in sev_above:
            elements.append(fl)
        elements.append(self._severity_summary_table(self.doc.severity_counts))
        for fl in sev_below:
            elements.append(fl)
        elements.append(Spacer(1, 24))

        # ── Finding details ────────────────────────────────────────
        elements.append(Paragraph(f"{self._heading_mark_prefix()}Detailed Findings", self.styles['SubSectionTitle']))
        elements.append(Spacer(1, 8))

        for item in self.doc.findings:
            head, body = self._finding_card(item)
            above, below = self._table_mark_flowables([item.mark])
            elements.extend(above)
            # Keep the header + meta together so a finding never starts with just
            # its title stranded at a page bottom; the body flows/splits freely.
            elements.append(KeepTogether(head))
            elements.extend(body)
            elements.extend(below)
            elements.append(Spacer(1, 8))
            self._render_evidence(elements, item)
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

    def _render_evidence(self, elements, item):
        """Embed images and list non-image attachments beneath a finding card."""
        evidence_list = item.evidence
        if not evidence_list:
            return

        font    = _t(self.theme, 'font_family')
        font_b  = _bold_font(font)
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
            mime = ev.mime

            # Effective mark for this evidence item (inherits the finding).
            ev_mark_raw = ev.mark.token
            ev_mark_esc = _escape_xml(ev_mark_raw)

            # Build caption (filename optional; mark-prefixed when CAPTION anchor).
            caption_parts = []
            if ev.description:
                caption_parts.append(ev.description)
            if show_filenames:
                caption_parts.append(f'[{ev.filename}]')
            caption_text = _escape_xml('  '.join(caption_parts))
            if ev_mark_esc and 'CAPTION' in anchors:
                caption_text = f'{ev_mark_esc}  {caption_text}'.strip()

            if mime in self._IMAGE_MIMES and self.storage:
                file_bytes = self._fetch_file_bytes(ev.storage_key)
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
                                              anchors=stamp_anchors, mark_fg=ev.mark.color)
                        else:
                            img = Image(img_stream)
                        iw, ih = img.imageWidth, img.imageHeight
                        if iw and ih:
                            scale = min(page_w / iw, max_img_h / ih, 1.0)
                            img.drawWidth  = iw * scale
                            img.drawHeight = ih * scale
                        img.hAlign = 'CENTER'
                        above_lines, below_lines = self._anchor_mark_lines(ev_mark_raw, overlay_anchors, ev.mark.color)
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
                        _log.warning(f'Could not embed image {ev.storage_key!r}: {exc}')

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

    # Test-case status → (key, label, hex). Darker shades read well on white paper.
    _TC_STATUS = {
        'pass': ('✓ Pass', '#16A34A'),
        'fail': ('✗ Fail', '#DC2626'),
        'exec': ('Executed · no verdict', '#2563EB'),
        'none': ('Not executed', '#64748B'),
    }

    def _render_testcases_section(self, elements, section):
        """Hierarchical test plan: one detail block per test case (parent → child),
        with a pass/fail status chip and markdown-rendered steps / expected /
        actual / notes and the findings each test discovered — modeled on the
        cleanup-artifact detail renderer."""
        elements.append(self._section_header_table(section.title.upper(), section))
        elements.append(Spacer(1, 16))

        if not self.testcases:
            elements.append(Paragraph('No test cases recorded.', self.styles['BodyText2']))
            elements.append(Spacer(1, 12))
            return

        font   = _t(self.theme, 'font_family')
        font_b = _bold_font(font)
        dark   = _t(self.theme, 'secondary_color')
        muted  = _t(self.theme, 'muted_text_color')

        # summary line
        summ = self.doc.testcase_summary
        total = summ['total']
        elements.append(Paragraph(
            f'{total} test case{"s" if total != 1 else ""} · {summ["executed"]} executed · '
            f'{summ["passed"]} passed · {summ["failed"]} failed',
            ParagraphStyle(name='TCSummary', parent=self.styles['BodyText2'], fontSize=9.5,
                           textColor=colors.HexColor(muted), spaceAfter=14)))

        for item in self.doc.testcases:
            t, depth, num = item.src, item.depth, item.number
            det_rows = []

            def _label(label):
                return Paragraph(label, ParagraphStyle(
                    name=f'TCL_{t.id}_{label}', parent=self.styles['Label'],
                    fontSize=8, fontName=font_b, textColor=colors.HexColor(muted)))

            def _add(label, val):
                if not val:
                    return
                det_rows.append([_label(label), Paragraph(_escape_xml(str(val)[:800]), ParagraphStyle(
                    name=f'TCV_{t.id}_{label}', parent=self.styles['BodyText2'], fontSize=9))])

            def _add_md(label, val, max_chars=50000):
                if not val:
                    return
                cs = ParagraphStyle(name=f'TCM_{t.id}_{label}', parent=self.styles['BodyText2'],
                                    fontSize=9, spaceAfter=2)
                fls = self._md_flowables(
                    str(val), cs, item.mark, max_chars=max_chars,
                    max_image_width=4.5 * inch, max_image_height=3.0 * inch)
                if fls:
                    det_rows.append([_label(label), fls])

            if item.category:
                _add('CATEGORY', item.category)
            for fld in item.fields:
                _add_md(fld.label.upper(), fld.markdown)
            if item.assets:
                _add('ASSETS', ', '.join(item.assets))
            if item.findings:
                fnames = ', '.join(
                    f'{_escape_xml(f.title)} ({f.severity.title()})' for f in item.findings)
                det_rows.append([_label('DISCOVERED FINDINGS'), Paragraph(fnames, ParagraphStyle(
                    name=f'TCF_{t.id}', parent=self.styles['BodyText2'], fontSize=9))])

            sc_label, sc_hex = self._TC_STATUS[item.status]
            indent = 14 + depth * 16
            title_p = Paragraph(f'{num}&nbsp;&nbsp;{self._mark_prefix(item.mark)}{_escape_xml(item.title)}',
                ParagraphStyle(name=f'TCTitle_{t.id}', parent=self.styles['FindingTitle'], fontSize=10))
            status_p = Paragraph(f'<b>{sc_label}</b>', ParagraphStyle(
                name=f'TCStatus_{t.id}', parent=self.styles['Normal'], fontSize=9, fontName=font_b,
                textColor=colors.HexColor(sc_hex), alignment=2))
            header = Table([[title_p, status_p]], colWidths=[5.0 * inch, 1.5 * inch])
            header.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(dark)),
                ('LEFTPADDING', (0, 0), (0, 0), indent),
                ('RIGHTPADDING', (1, 0), (1, 0), 12),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LINEBEFORE', (0, 0), (0, 0), 4, colors.HexColor(sc_hex)),
            ]))

            tc_above, tc_below = self._table_mark_flowables([item.mark])
            block = [header]
            if det_rows:
                # splitInRow: a field taller than a page splits inside its row
                # (a row that can't split aborted the whole PDF with LayoutError).
                body_t = Table(det_rows, colWidths=[1.3 * inch, 5.2 * inch], splitInRow=1)
                body_t.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('TOPPADDING', (0, 0), (-1, -1), 6),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                    ('LEFTPADDING', (0, 0), (0, -1), indent),
                    ('LEFTPADDING', (1, 0), (1, -1), 8),
                    ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
                    ('LINEBELOW', (0, 0), (-1, -2), 0.25, colors.HexColor('#E2E8F0')),
                    ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
                ]))
                block.append(body_t)
            elements.append(KeepTogether(tc_above + block + tc_below))
            elements.append(Spacer(1, 10))
        elements.append(Spacer(1, 10))

    def _render_cleanup_artifacts_section(self, elements, section):
        elements.append(self._section_header_table(section.title.upper(), section))
        elements.append(Spacer(1, 16))

        if not self.cleanup_artifacts:
            elements.append(Paragraph('No cleanup artifacts recorded.', self.styles['BodyText2']))
            elements.append(Spacer(1, 12))
            return

        font   = _t(self.theme, 'font_family')
        font_b = _bold_font(font)
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
            header_cells = [self._row_mark_cell(header=True)] + header_cells
        rows = [header_cells]

        for ca in self.doc.cleanup:
            cells = [
                Paragraph(_escape_xml(ca.title[:60]), cell_style),
                Paragraph(_escape_xml(ca.artifact_type), cell_style),
                Paragraph(_escape_xml(ca.status), cell_style),
                Paragraph(_escape_xml((ca.location or 'N/A')[:50]), cell_style),
            ]
            if per_row:
                cells = [self._row_mark_cell(ca.mark)] + cells
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

        above, below = self._table_mark_flowables([ca.mark for ca in self.doc.cleanup])
        for fl in above:
            elements.append(fl)
        elements.append(t)
        for fl in below:
            elements.append(fl)

        # Detailed entries
        elements.append(Spacer(1, 24))
        for idx, ca in enumerate(self.doc.cleanup, 1):
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

            def _add_md(label, val, max_chars=50000):
                """Markdown row — renders block-level markdown into the cell."""
                if not val:
                    return
                cell_style = ParagraphStyle(
                    name=f'CAV_{idx}_{label}', parent=self.styles['BodyText2'],
                    fontSize=9, spaceAfter=2,
                )
                flowables = self._md_flowables(
                    str(val), cell_style, ca.mark, max_chars=max_chars,
                    max_image_width=4.5 * inch, max_image_height=3.0 * inch,
                )
                if not flowables:
                    return
                det_rows.append([_label(label), flowables])

            _add('TYPE', ca.artifact_type)
            _add('STATUS', ca.status)
            if ca.location:
                _add('LOCATION', ca.location)
            for fld in ca.fields:
                _add_md(fld.label.upper(), fld.markdown)
            if ca.assets:
                _add('ASSETS', ', '.join(ca.assets))

            if det_rows:
                header = Table(
                    [[Paragraph(f'{idx}. {self._mark_prefix(ca.mark)}{_escape_xml(ca.title)}', ParagraphStyle(
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
                # splitInRow: a field taller than a page splits inside its row
                # (a row that can't split aborted the whole PDF with LayoutError).
                body_t = Table(det_rows, colWidths=[1.3 * inch, 5.2 * inch], splitInRow=1)
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
                ca_above, ca_below = self._table_mark_flowables([ca.mark])
                elements.append(KeepTogether(ca_above + [header, body_t] + ca_below))
                elements.append(Spacer(1, 12))


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


# ═══════════════════════════════════════════════════════════════════
# HTML Report Generator — self-contained, styled, marking-aware
# ═══════════════════════════════════════════════════════════════════

def _markdown_without_raw_html(text: str) -> str:
    """Render markdown with raw HTML switched off: Python-Markdown's HTML
    block preprocessor and inline-HTML pattern are removed, so author
    content can't inject <script> / <img onerror=…> (any "<…>" is output
    as escaped text) while all markdown syntax still works. Escaping the
    source first instead (the previous approach) double-escaped code
    ("&lt;" shown literally) and turned "> quote" into "&gt; quote".
    Dangerous URL schemes in links are stripped by the caller."""
    import markdown as _markdown
    md = _markdown.Markdown(extensions=['extra', 'sane_lists', 'nl2br'])
    md.preprocessors.deregister('html_block')
    md.inlinePatterns.deregister('html')
    return md.convert(text)


class HTMLReportGenerator:
    """Produces a single self-contained HTML document (inline CSS, base64
    images) — an editable deliverable clients can open in a browser or import
    into Word. Honors the theme palette and the marking profile (banner +
    portion marks)."""

    def __init__(self, engagement, sections, findings, testcases,
                 cleanup_artifacts=None, theme=None, storage=None,
                 markdown_image_map=None, marking_profile=None,
                 finding_custom_fields=None, chain_edges=None,
                 chain_vault_items=None):
        self.engagement = engagement
        self.theme = theme
        self.storage = storage
        self.doc = build_report_document(
            engagement, sections, findings, testcases, cleanup_artifacts,
            theme=theme, marking_profile=marking_profile,
            finding_custom_fields=finding_custom_fields,
            default_title=_DEFAULTS['cover_title'])
        # Operator-authored attack-chain edges (ChainLink) + touched vault
        # items. Empty → payload's `chain` is [] and the interactive graph
        # renders exactly as before.
        self.chain_edges = chain_edges or []
        self.chain_vault_items = chain_vault_items or {}
        self.markdown_image_map = markdown_image_map or {}
        self.marking = self.doc.marking

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
        try:
            html = _markdown_without_raw_html(str(text))
        except Exception:
            html = '<p>' + _escape_xml(str(text)).replace('\n', '<br/>') + '</p>'
        # Neutralize dangerous URL schemes markdown may emit from links like
        # [x](javascript:…). Our own embedded images (data: URIs) are added by
        # _rewrite_inline_images *after* this strip, so they are unaffected.
        html = re.sub(r'(?i)(href|src)\s*=\s*"\s*(?:javascript|vbscript|data):[^"]*"', r'\1="#"', html)
        return self._rewrite_inline_images(html)

    # ── generate ──────────────────────────────────────────────────

    # ── interactive report: build data + inject into the app template ──
    def _build_report_data(self):
        doc = self.doc
        eng = self.engagement
        fid = {f.id: f.ref for f in doc.findings}
        tid = {t.id: t.ref for t in doc.testcases}

        findings = []
        for f in doc.findings:
            ev = []
            for e in f.evidence:
                if e.is_image:
                    uri = self._data_uri(e.storage_key, e.mime)
                    if uri:
                        ev.append({'img': uri, 'cap': _escape_xml(e.description or e.filename),
                                   'mark': e.mark.token})
            src, si = f.src, f.score
            findings.append({
                'id': f.ref, 'sev': f.severity.lower(), 'status': f.status_group,
                # 'cvss' stays numeric for sorting (nominal for categorical
                # models); 'num' says whether it is a real score to display.
                'cvss': (round(float(src.cvss_score), 1) if src.cvss_score is not None else 0),
                'num': si['numeric'], 'model': si['label'], 'outcome': si['outcome'] or '',
                'vec': src.cvss_vector or '—',
                'cwe': f.category,
                'mark': f.mark.token, 'title': f.title,
                'assets': [a.name for a in f.assets],
                'desc': self._md(src.description), 'impact': self._md(src.impact), 'biz': '',
                'steps': self._md(src.steps_to_reproduce), 'tech': self._md(src.technical_details),
                'remed': self._md(src.mitigations),
                'refs_html': self._md(src.references) if src.references else '',
                'custom': [[label, value] for label, value in f.custom_fields],
                'ev': ev,
            })

        testcases = []
        for t in doc.testcases:
            src = t.src
            testcases.append({
                'id': t.ref, 'label': t.title, 'status': t.status_label, 'mark': t.mark.token,
                'parent': t.parent_ref,
                'finds': [x.ref for x in t.findings if x.ref],
                'desc': self._md(src.description), 'steps': self._md(src.steps),
                'expected': self._md(src.expected_result), 'actual': self._md(src.actual_result),
                'notes': self._md(src.notes),
            })

        asset_map = {}
        for f in doc.findings:
            for a in f.assets:
                d = asset_map.setdefault(a.name, {'n': a.name, 'type': a.asset_type, 'sevs': {}})
                sev = f.severity.lower()
                d['sevs'][sev] = d['sevs'].get(sev, 0) + 1
        assets = list(asset_map.values())

        cleanup = []
        for ca in doc.cleanup:
            src = ca.src
            cleanup.append({
                't': ca.title, 'type': ca.artifact_type, 'sys': ca.location, 'owner': '',
                'status': ca.status, 'mark': ca.mark.token,
                'finding': ca.finding_refs[0] if ca.finding_refs else None,
                'asset': ca.assets[0] if ca.assets else None,
                'note': _escape_xml((src.description or src.cleanup_notes or '')[:400]),
            })

        rating = doc.findings[0].severity if doc.findings else 'INFO'
        cvsses = [f.src.cvss_score for f in doc.findings if f.src.cvss_score]
        score = max(cvsses) if cvsses else {'CRITICAL': 9.5, 'HIGH': 7.5, 'MEDIUM': 5.0,
                                             'LOW': 3.0, 'INFO': 0.5}.get(rating, 0)
        top = doc.findings[0].title if doc.findings else ''
        n = len(doc.findings)
        risk = {
            'rating': rating, 'score': round(float(score), 1),
            'caption': (f'Overall risk posture · driven by {top}' if top else 'Overall risk posture'),
            'summary_html': self._md(getattr(eng, 'description', None)) if getattr(eng, 'description', None) else '',
            'subtitle': f'{n} finding{"s" if n != 1 else ""} confirmed across this engagement.',
        }

        marking = {}
        if doc.banner:
            marking = {'banner': doc.banner.text,
                       'caption': (getattr(doc.marking, 'distribution_statement', '') or '')}

        window = ''
        sd, ed = getattr(eng, 'start_date', None), getattr(eng, 'end_date', None)
        if sd and ed:
            window = f'{sd.strftime("%b %d").replace(" 0", " ")} – {ed.strftime("%b %d, %Y").replace(" 0", " ")}'
        ref = _t(self.theme, 'report_reference') or ''
        ver = _t(self.theme, 'report_version') or ''
        ref_full = (f'{ref} · {ver}' if ref and ver else (ref or ver))
        team = len(getattr(eng, 'assigned_users', None) or [])
        eng_type = _title_case(getattr(eng, 'engagement_type', None)) or (eng.name or 'Engagement')

        fields = [['Client', eng.client_name or '—', None], ['Engagement', eng_type, None]]
        if window:
            fields.append(['Window', window, None])
        if ref_full:
            fields.append(['Report ref', ref_full, None])
        fields.append(['Prepared by', 'RedWire', None])
        if team:
            fields.append(['Team', f'{team} operator{"s" if team != 1 else ""}', None])
        if marking.get('banner'):
            fields.append(['Classification', marking['banner'], '#FFC000'])
        fields.append(['Findings', f'{n} confirmed', None])
        models = sorted({f.score['label'] for f in doc.findings})
        if models:
            fields.append(['Scoring', ' · '.join(models), None])

        meta = {
            'title': doc.title,
            'client': eng.client_name or eng.name, 'engagement': eng_type,
            'ref': ref_full, 'summary': '', 'fields': fields,
        }

        # Attack-chain overlay: resolve operator-authored ChainLink edges into
        # the interactive graph's display-id space (F##/T#; vault → 'vault-<id>').
        # Vault items aren't otherwise in the report, so surface the ones a chain
        # touches. When there are no chain edges this yields chain=[] and no
        # chainVault key.
        cv_nodes, c_edges, _ = _resolve_chain_edges(
            self.chain_edges, tid, fid, self.chain_vault_items)
        chain = [{'s': e['s'], 't': e['t'], 'note': e.get('note') or ''} for e in c_edges]

        data = {'meta': meta, 'risk': risk, 'marking': marking, 'findings': findings,
                'testcases': testcases, 'assets': assets, 'cleanup': cleanup, 'chain': chain}
        if cv_nodes:
            data['chainVault'] = [
                {'id': v['id'], 'label': v['label'], 'itype': v['itype']} for v in cv_nodes
            ]
        return data

    def generate(self) -> str:
        """Portable, offline, interactive HTML report — a self-contained app whose
        data is injected as ``window.__REPORT__`` (markdown pre-rendered, images
        embedded as data URIs). Replaces the old single-page HTML clone."""
        import json as _json
        import os as _os
        data = self._build_report_data()
        tmpl_path = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)),
                                  'report_templates', 'interactive', 'report.template.html')
        with open(tmpl_path, 'r', encoding='utf-8') as fh:
            tmpl = fh.read()
        # ``</`` is escaped so a field can never break out of the <script> tag.
        payload = 'window.__REPORT__ = ' + _json.dumps(data, ensure_ascii=False).replace('</', '<\\/') + ';'
        return tmpl.replace('/*__REPORT_DATA__*/', payload, 1)
