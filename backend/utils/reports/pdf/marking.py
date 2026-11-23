"""PDF report — portion-marking helpers: banners, heading and table marks, cover marking block."""
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph
from utils.reports.content import Mark, NO_MARK
from utils.reports.common import _escape_xml, _t
from utils.reports.pdf.text import _bold_font


class MarkingMixin:
    """Portion-marking helpers: banners, heading and table marks, cover marking block."""

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
