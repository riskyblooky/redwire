"""Classification / portion-marking engine for report generation.

Reads a MarkingProfile (the ladder + scheme + placement policy) and an
Engagement (document-wide default + ceiling). Pure logic + a couple of small
ReportLab helpers; the PDF generator owns all layout decisions and calls in
here for resolution, roll-up, and mark formatting.

Design (see docs/report-generation-and-portion-marking.md):
  - Inheritance (top-down): a portion with no explicit level inherits the
    engagement default; the result is clamped to the engagement ceiling.
  - Roll-up (bottom-up): the banner is the highest *effective* level of any
    portion — computed, never set.
  - Two idioms keyed off `scheme`: TLP 2.0 (right-justified header banner,
    `TLP:AMBER` tokens) and IC/DoD + custom (centered top+bottom banner,
    `(S)` parenthetical tokens).
  - The free-text suffix (e.g. `//SAR/123`) is carried verbatim onto portion
    marks but never participates in ranking.
"""
from typing import Optional, List, Tuple

from reportlab.platypus import Image
from reportlab.lib import colors


class MarkingEngine:
    def __init__(self, profile, engagement):
        self.profile = profile
        self.engagement = engagement
        self.scheme = getattr(getattr(profile, "scheme", None), "value", getattr(profile, "scheme", None))

        self.levels_by_abbr = {}
        self._ordered: List[dict] = []
        for lvl in (getattr(profile, "levels", None) or []):
            abbr = lvl.get("abbreviation")
            if abbr:
                self.levels_by_abbr[abbr] = lvl
                self._ordered.append(lvl)

    # ── ranking / roll-up ────────────────────────────────────────────
    def _rank(self, abbr: Optional[str]) -> int:
        if not abbr:
            return -1
        lvl = self.levels_by_abbr.get(abbr)
        return lvl.get("rank", -1) if lvl else -1

    def highest(self, abbrs) -> Optional[str]:
        best, best_rank = None, -1
        for a in abbrs:
            if not a:
                continue
            r = self._rank(a)
            if r > best_rank:
                best, best_rank = a, r
        return best

    def lowest_level(self) -> Optional[str]:
        """Abbreviation of the lowest-rank level (e.g. U / TLP:CLEAR)."""
        if not self._ordered:
            return None
        return min(self._ordered, key=lambda l: l.get("rank", 0)).get("abbreviation")

    @property
    def static_heading_mode(self) -> str:
        """How structural headings are marked: 'LOWEST' (default) or 'INHERIT'."""
        return getattr(self.profile, "static_heading_marks", None) or "LOWEST"

    # ── resolution ───────────────────────────────────────────────────
    def resolve(self, level: Optional[str], suffix: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
        """Effective (level, suffix) for one portion:
        explicit → engagement default → clamp to ceiling."""
        if level:
            eff_level, eff_suffix = level, suffix
        else:
            eff_level = getattr(self.engagement, "default_classification_level", None)
            eff_suffix = getattr(self.engagement, "default_classification_suffix", None)

        ceiling = getattr(self.engagement, "ceiling_classification_level", None)
        if ceiling and self._rank(eff_level) > self._rank(ceiling):
            # Over-ceiling portions are clamped down; the caveat is dropped with
            # the level it belonged to.
            eff_level, eff_suffix = ceiling, None
        return eff_level, eff_suffix

    # ── scheme flags ─────────────────────────────────────────────────
    @property
    def is_tlp(self) -> bool:
        return self.scheme == "TLP_2_0"

    @property
    def inline_marks(self) -> bool:
        """Whether inline portion marks render. False → banner-only (TLP style)."""
        v = getattr(self.profile, "inline_portion_marks", None)
        return True if v is None else bool(v)

    @property
    def banner_top_and_bottom(self) -> bool:
        # IC/DoD and custom ladders use a centered banner top *and* bottom;
        # TLP uses a single right-justified header line.
        return not self.is_tlp

    # ── placement policy passthrough ─────────────────────────────────
    @property
    def image_anchors(self) -> List[str]:
        return list(getattr(self.profile, "image_mark_anchors", None) or [])

    @property
    def table_anchors(self) -> List[str]:
        return list(getattr(self.profile, "table_mark_anchors", None) or [])

    @property
    def per_row(self) -> bool:
        return bool(getattr(self.profile, "table_per_row_marks", False))

    @property
    def stamp_images(self) -> bool:
        return bool(getattr(self.profile, "stamp_images", False))

    @property
    def show_legend(self) -> bool:
        return bool(getattr(self.profile, "show_legend", True))

    @property
    def distribution_statement(self) -> Optional[str]:
        return getattr(self.profile, "distribution_statement", None)

    # ── rendering ────────────────────────────────────────────────────
    def portion_mark(self, level: Optional[str], suffix: Optional[str]) -> str:
        """Inline token for a portion (raw text — caller escapes for Paragraph).

        TLP: `TLP:AMBER`   IC/custom: `(S)` / `(S//SAR/123)`.
        """
        if not level or not self.inline_marks:
            return ""
        suffix = suffix or ""
        if self.is_tlp:
            return f"TLP:{level}{suffix}"
        return f"({level}{suffix})"

    def banner(self, level: Optional[str]) -> Optional[Tuple[str, str, str]]:
        """(text, bg_color, text_color) for the page/document banner, or None."""
        if not level:
            return None
        lvl = self.levels_by_abbr.get(level)
        if not lvl:
            return None
        text = lvl.get("full_name") or (f"TLP:{level}" if self.is_tlp else level)
        return text, lvl.get("banner_color") or "#1E293B", lvl.get("text_color") or "#FFFFFF"

    def legend_entries(self) -> List[Tuple[str, str, str, str]]:
        """(abbreviation, full_name, banner_color, text_color) for each level."""
        return [
            (
                l.get("abbreviation", ""),
                l.get("full_name", ""),
                l.get("banner_color") or "#1E293B",
                l.get("text_color") or "#FFFFFF",
            )
            for l in self._ordered
        ]


# ── Anchor geometry ──────────────────────────────────────────────────
# Corner/edge marks drawn directly on an image bitmap so a detached screenshot
# stays marked. CAPTION is handled by the generator as a caption paragraph, not
# here.
_OVERLAY_ANCHORS = {
    "TOP_LEFT", "TOP_CENTER", "TOP_RIGHT",
    "BOTTOM_LEFT", "BOTTOM_CENTER", "BOTTOM_RIGHT",
}


def lint_marking(engine, sections, findings, testcases, cleanup_artifacts):
    """Pre-generation marking lint.

    Returns (blocking, warnings):
      - blocking: portions whose *effective* level is None (no explicit mark and
        no engagement default) — these would render unmarked.
      - warnings: portions with no *explicit* mark that resolve to a level via
        inheritance (riding the inherited default) — a review aid.

    Evidence inherits its finding's effective mark (mirrors the generator).
    """
    # Banner-only profiles (e.g. TLP) have no inline portion marks to enforce.
    if not engine.inline_marks:
        return [], []
    blocking, warnings = [], []

    def assess(label, entity, parent_eff=None):
        lvl = getattr(entity, "classification_level", None)
        suf = getattr(entity, "classification_suffix", None)
        explicit = bool(lvl)
        if explicit:
            eff, _ = engine.resolve(lvl, suf)
        elif parent_eff:
            eff = parent_eff
        else:
            eff, _ = engine.resolve(None, None)  # → engagement default (or None)
        if not eff:
            blocking.append(label)
        elif not explicit:
            warnings.append(label)
        return eff

    for s in sections:
        assess(f"Section: {getattr(s, 'title', '?')}", s)
    for f in findings:
        f_eff = assess(f"Finding: {getattr(f, 'title', '?')}", f)
        for ev in (getattr(f, "evidence", None) or []):
            if getattr(ev, "include_in_report", False):
                assess(f"Evidence: {getattr(ev, 'original_filename', '?')}", ev, parent_eff=f_eff)
    for tc in testcases:
        assess(f"Test case: {getattr(tc, 'title', '?')}", tc)
    for ca in cleanup_artifacts:
        assess(f"Cleanup artifact: {getattr(ca, 'title', '?')}", ca)

    return blocking, warnings


class MarkedImage(Image):
    """An Image flowable that overprints a classification token at one or more
    corner/edge anchors after drawing the bitmap."""

    def __init__(self, *args, mark_text: str = "", anchors=None,
                 mark_fg: str = "#B91C1C", **kwargs):
        super().__init__(*args, **kwargs)
        self._mark_text = mark_text or ""
        self._anchors = [a for a in (anchors or []) if a in _OVERLAY_ANCHORS]
        self._mark_fg = mark_fg

    def draw(self):
        Image.draw(self)
        if not self._mark_text or not self._anchors:
            return
        c = self.canv
        font, size, pad = "Helvetica-Bold", 7, 3
        w, h = self.drawWidth, self.drawHeight
        tw = c.stringWidth(self._mark_text, font, size)
        th = size
        c.saveState()
        c.setFont(font, size)
        for anchor in self._anchors:
            vert, horiz = anchor.split("_")
            if horiz == "LEFT":
                x = pad
            elif horiz == "RIGHT":
                x = w - tw - pad
            else:
                x = (w - tw) / 2.0
            y = (h - th - pad) if vert == "TOP" else pad
            # White pad box behind the text for legibility over any image.
            c.setFillColor(colors.white)
            c.rect(x - 1.5, y - 1.5, tw + 3, th + 3, fill=1, stroke=0)
            c.setFillColor(colors.HexColor(self._mark_fg))
            c.drawString(x, y, self._mark_text)
        c.restoreState()
