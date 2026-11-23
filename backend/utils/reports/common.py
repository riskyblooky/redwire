"""Helpers shared by every report format: theme lookups, severity colours, attack-chain resolution."""
from models.report_theme import ReportTheme
from typing import Optional
from utils.reports.content import SEVERITY_ORDER


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
