"""PDF report — cover page, page header/footer, table of contents and section header bars."""
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Paragraph, Spacer, Table, TableStyle
from reportlab.platypus.tableofcontents import TableOfContents
from utils.reports.content import _v
from utils.reports.common import _escape_xml, _t
from utils.reports.pdf.page import _decode_logo
from utils.reports.pdf.text import _bold_font


class CoverMixin:
    """Cover page, page header/footer, table of contents and section header bars."""

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
