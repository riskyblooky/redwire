"""PDF report — executive overview: severity summary table, donut, metric tiles, exposure chart."""
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Paragraph, Spacer, Table, TableStyle
from utils.reports.content import _score_info, _score_label, _v
from utils.reports.common import _SEV_ORDER, _escape_xml, _t
from utils.reports.pdf.text import _bold_font


class OverviewMixin:
    """Executive overview: severity summary table, donut, metric tiles, exposure chart."""

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
