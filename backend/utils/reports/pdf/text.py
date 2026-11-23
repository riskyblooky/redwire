"""Markdown → ReportLab: inline markup and block flowables for the PDF report."""
import logging
import io
import re
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import Image, Paragraph, Spacer, Table, TableStyle
from typing import Optional
from utils.marking import MarkedImage
from utils.reports.common import _escape_xml

_log = logging.getLogger(__name__)


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
