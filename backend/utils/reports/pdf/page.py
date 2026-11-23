"""PDF page plumbing: page sizes, logo decoding, outline-aware doc template, numbered canvas."""
import base64
import io
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, letter
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import SimpleDocTemplate
from typing import Optional


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
