"""What a report says, separate from how each format lays it out.

``build_report_document`` turns the loaded rows (engagement, layout sections,
findings, test cases, cleanup items) plus the marking profile into one
``ReportDocument``. The PDF, Markdown and interactive HTML renderers in
``utils/reports/`` (``pdf/``, ``markdown_report.py``, ``html_report.py``) each keep their own layout code but take every
decision about *content* from it:

- order: findings most-severe first, test cases as a parent → child tree;
- display ids (``F01``, ``T1``) and hierarchical test-case numbers (``1.2``);
- which fields a finding / test case / cleanup item shows, under which label;
- statuses (test case pass / fail / executed / not executed, finding status
  group), score presentation, report-visible custom fields, linked assets and
  findings, included evidence;
- portion marking: each portion's effective mark (explicit → engagement
  default → ceiling clamp; evidence inherits its finding), structural-heading
  marks, and the document banner (the high-water mark of every portion).

These used to be worked out separately by each renderer, and had drifted: the
Markdown export carried no marks or banner, technical details appeared only in
the HTML report, test-case status had three states in one format and four in
another, and test-case display ids didn't match between the PDF's graph and its
test-case section.

Nothing here touches the database or storage; rows must arrive with the
relationships the report uses already loaded (see ``routers/reports.py``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from scoring.display import outcome_label
from scoring.registry import DEFAULT_MODEL_ID, scoring_registry
from utils.marking import MarkingEngine


# ── small shared helpers (also used by the renderers) ─────────────

_SEVERITY_RANK = {'CRITICAL': 5, 'HIGH': 4, 'MEDIUM': 3, 'LOW': 2, 'INFO': 1}
SEVERITY_ORDER = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO']


def _v(val) -> str:
    if val is None:
        return 'N/A'
    return val.value if hasattr(val, 'value') else str(val)


def _severity_rank(severity) -> int:
    return _SEVERITY_RANK.get(_v(severity).upper(), 0)


def _title_case(val) -> str:
    return _v(val).replace('_', ' ').title() if val else ''


def _format_report_cf_value(field_type, value) -> Optional[str]:
    """Display string for a custom-field value in a report, or None if empty."""
    if value is None or value == "" or value == []:
        return None
    if field_type == "boolean":
        return "Yes" if value else "No"
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value)


def _report_cf_rows(defs, custom_fields) -> list:
    """(label, display_value) pairs for report-visible custom fields that have
    a value on this record. ``defs`` is the precomputed show_in_report
    definition list; ``custom_fields`` is the record's JSON dict (may be None)."""
    cf = custom_fields or {}
    rows = []
    for d in (defs or []):
        v = _format_report_cf_value(d.field_type, cf.get(d.field_key))
        if v is not None:
            rows.append((d.label, v))
    return rows


def _score_info(finding) -> dict:
    """How a finding's rating should be presented, given the scoring model that
    produced it. Legacy findings (no ``score_model``) are CVSS 3.1.

    Returns ``label`` (model name, e.g. "USAF Risk Assessment Matrix"),
    ``numeric`` (False for categorical models, whose ``cvss_score`` is only a
    nominal sort key and must not be printed as a score), ``score``,
    ``outcome`` (categorical display label), ``vector`` and ``text`` (one-line
    display string, '' when unscored).
    """
    model_id = getattr(finding, 'score_model', None) or DEFAULT_MODEL_ID
    model = scoring_registry.get(model_id)
    label = model.label if model else 'Score'
    numeric = model is None or model.score_kind == 'numeric'
    score = float(finding.cvss_score) if numeric and finding.cvss_score is not None else None
    outcome = None if numeric else outcome_label(model_id, getattr(finding, 'score_inputs', None))
    vector = finding.cvss_vector or None
    head = f'{score:.1f}' if score is not None else (outcome or '')
    text = f'{head}  |  {vector}' if head and vector else (head or vector or '')
    return {'label': label, 'numeric': numeric, 'score': score, 'outcome': outcome,
            'vector': vector, 'text': text}


def _score_label(findings) -> str:
    """Overall label for scores across several findings: the shared model's name
    when all scored findings use one model, else a generic 'Score'."""
    labels = {_score_info(f)['label'] for f in findings}
    return labels.pop() if len(labels) == 1 else 'Score'


# Finding status → the interactive report's three status groups.
_STATUS_GROUP = {
    'OPEN': 'open', 'IN_PROGRESS': 'progress', 'REMEDIATED': 'remediated',
    'RESOLVED': 'remediated', 'CLOSED': 'remediated', 'FIXED': 'remediated',
    'ACCEPTED': 'open', 'FALSE_POSITIVE': 'remediated',
}


def finding_status_group(status) -> str:
    s = _v(status).upper()
    if s in _STATUS_GROUP:
        return _STATUS_GROUP[s]
    if 'PROGRESS' in s:
        return 'progress'
    if any(k in s for k in ('RESOLV', 'REMEDI', 'CLOS', 'FIX')):
        return 'remediated'
    return 'open'


# Test-case status: key → display label.
TESTCASE_STATUS_LABELS = {
    'pass': 'Pass',
    'fail': 'Fail',
    'exec': 'Executed',
    'none': 'Not Executed',
}


def testcase_status(tc) -> str:
    if getattr(tc, 'is_successful', None) is True:
        return 'pass'
    if getattr(tc, 'is_successful', None) is False:
        return 'fail'
    if getattr(tc, 'is_executed', None):
        return 'exec'
    return 'none'


# ── the document ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Mark:
    """One portion's effective classification. ``token`` is the inline mark
    ('(S//NF)', 'TLP:AMBER'), '' when marking is off or the profile is
    banner-only; ``color`` tints marks drawn on images and tables."""
    level: Optional[str] = None
    suffix: Optional[str] = None
    token: str = ''
    color: str = '#B91C1C'

    def __bool__(self) -> bool:
        return bool(self.level)

    @property
    def pair(self) -> tuple:
        return (self.level, self.suffix)


NO_MARK = Mark()


@dataclass(frozen=True)
class Banner:
    level: str
    text: str
    bg: str
    fg: str


@dataclass
class Field:
    """A markdown body field (description, impact, ...)."""
    key: str
    label: str
    markdown: str


@dataclass
class EvidenceItem:
    src: Any
    id: str
    storage_key: Optional[str]
    mime: str
    description: str
    filename: str
    mark: Mark

    @property
    def is_image(self) -> bool:
        return self.mime.startswith('image/')


@dataclass
class AssetRef:
    name: str
    asset_type: str


@dataclass
class FindingItem:
    src: Any
    id: str
    ref: str                  # F01
    title: str
    severity: str             # CRITICAL ... INFO
    status: str               # raw status value
    status_group: str         # open | progress | remediated
    score: dict               # _score_info()
    category: str
    assets: list[AssetRef]
    fields: list[Field]
    custom_fields: list[tuple[str, str]]
    evidence: list[EvidenceItem]
    mark: Mark


@dataclass
class LinkedFinding:
    ref: Optional[str]        # None when the finding isn't in this report
    title: str
    severity: str


@dataclass
class TestcaseItem:
    src: Any
    id: str
    ref: str                  # T1 (tree order)
    number: str               # 1.2 (position in the tree)
    depth: int
    parent_ref: Optional[str]
    title: str
    category: str
    status: str               # pass | fail | exec | none
    fields: list[Field]
    assets: list[str]
    findings: list[LinkedFinding]
    mark: Mark

    @property
    def status_label(self) -> str:
        return TESTCASE_STATUS_LABELS[self.status]


@dataclass
class CleanupItem:
    src: Any
    id: str
    title: str
    artifact_type: str
    status: str
    location: str
    fields: list[Field]
    assets: list[str]
    finding_refs: list[str]
    mark: Mark


@dataclass
class SectionBlock:
    src: Any
    kind: str                 # TEXT | FINDINGS | TESTCASES | CLEANUP_ARTIFACTS
    title: str
    content: str              # markdown (TEXT sections)
    heading_mark: Mark        # explicit section mark, else the structural mark
    mark: Mark                # the section content's effective mark
    page_break_before: bool


@dataclass
class ReportDocument:
    engagement: Any
    title: str
    client: str
    engagement_name: str
    generated_on: date
    marking: Optional[MarkingEngine]
    sections: list[SectionBlock]
    findings: list[FindingItem]
    testcases: list[TestcaseItem]
    cleanup: list[CleanupItem]
    banner: Optional[Banner]
    structural_mark: Mark     # unmarked structural headings
    default_mark: Mark        # aggregates (severity chart) carry the engagement default
    severity_counts: dict[str, int] = field(default_factory=dict)

    @property
    def banner_level(self) -> Optional[str]:
        return self.banner.level if self.banner else None

    @property
    def testcase_summary(self) -> dict:
        st = [t.status for t in self.testcases]
        return {'total': len(st), 'executed': sum(1 for t in self.testcases if getattr(t.src, 'is_executed', None)),
                'passed': st.count('pass'), 'failed': st.count('fail')}

    def table_mark(self, marks) -> Mark:
        """The mark for a table or aggregate of portions: the highest-ranked
        one, carrying its suffix."""
        best, best_rank = NO_MARK, -1
        for m in marks:
            if not m or not self.marking:
                continue
            r = self.marking._rank(m.level)
            if r > best_rank:
                best, best_rank = m, r
        return best

    def finding(self, finding_id) -> Optional[FindingItem]:
        return self._findings_by_id.get(finding_id)

    def testcase(self, tc_id) -> Optional[TestcaseItem]:
        return self._testcases_by_id.get(tc_id)

    def __post_init__(self):
        self._findings_by_id = {f.id: f for f in self.findings}
        self._testcases_by_id = {t.id: t for t in self.testcases}


_FINDING_FIELDS = [
    ('description', 'Description'),
    ('impact', 'Impact'),
    ('steps_to_reproduce', 'Steps to Reproduce'),
    ('technical_details', 'Technical Details'),
    ('mitigations', 'Recommendations'),
    ('references', 'References'),
]
_TESTCASE_FIELDS = [
    ('description', 'Description'),
    ('steps', 'Steps'),
    ('expected_result', 'Expected Result'),
    ('actual_result', 'Actual Result'),
    ('notes', 'Notes'),
]
_CLEANUP_FIELDS = [
    ('description', 'Description'),
    ('cleanup_notes', 'Cleanup Notes'),
]


def _fields(obj, spec) -> list[Field]:
    out = []
    for key, label in spec:
        val = getattr(obj, key, None)
        if val:
            out.append(Field(key, label, str(val)))
    return out


class _Marker:
    """Effective marks under one profile (or none)."""

    def __init__(self, engine: Optional[MarkingEngine]):
        self.engine = engine

    def mark(self, level, suffix) -> Mark:
        e = self.engine
        if not e:
            return NO_MARK
        lvl, suf = e.resolve(level, suffix)
        if not lvl:
            return NO_MARK
        b = e.banner(lvl)
        return Mark(lvl, suf, e.portion_mark(lvl, suf), b[1] if b else '#B91C1C')

    def of(self, entity) -> Mark:
        return self.mark(getattr(entity, 'classification_level', None),
                         getattr(entity, 'classification_suffix', None))

    def structural(self) -> Mark:
        """Unmarked structural headings: the profile's lowest level, or the
        engagement default when static_heading_marks is INHERIT."""
        e = self.engine
        if not e:
            return NO_MARK
        if e.static_heading_mode == 'INHERIT':
            return self.mark(None, None)
        lvl = e.lowest_level()
        if not lvl:
            return NO_MARK
        b = e.banner(lvl)
        return Mark(lvl, None, e.portion_mark(lvl, None), b[1] if b else '#B91C1C')


def build_report_document(engagement, sections, findings, testcases, cleanup_artifacts=None,
                          theme=None, marking_profile=None, finding_custom_fields=None,
                          default_title='Red Team Assessment Report') -> ReportDocument:
    engine = MarkingEngine(marking_profile, engagement) if marking_profile else None
    mk = _Marker(engine)
    structural = mk.structural()

    # Findings, most severe first (stable for equal severity).
    ordered = sorted(findings or [], key=lambda f: _severity_rank(f.severity), reverse=True)
    f_items: list[FindingItem] = []
    for i, f in enumerate(ordered, 1):
        fmark = mk.of(f)
        evidence = []
        for e in (getattr(f, 'evidence', None) or []):
            if not getattr(e, 'include_in_report', False):
                continue
            emark = mk.of(e) if getattr(e, 'classification_level', None) else fmark
            evidence.append(EvidenceItem(
                src=e, id=e.id, storage_key=getattr(e, 'filename', None),
                mime=(getattr(e, 'mime_type', None) or '').lower(),
                description=getattr(e, 'description', None) or '',
                filename=getattr(e, 'original_filename', None) or '', mark=emark))
        f_items.append(FindingItem(
            src=f, id=f.id, ref=f'F{i:02d}', title=f.title or 'Untitled',
            severity=_v(f.severity).upper(), status=_v(getattr(f, 'status', None)),
            status_group=finding_status_group(getattr(f, 'status', None)),
            score=_score_info(f), category=_title_case(getattr(f, 'category', None)),
            assets=[AssetRef(a.name, _title_case(getattr(a, 'asset_type', None)) or 'Asset')
                    for a in (getattr(f, 'assets', None) or [])],
            fields=_fields(f, _FINDING_FIELDS),
            custom_fields=_report_cf_rows(finding_custom_fields, getattr(f, 'custom_fields', None)),
            evidence=evidence, mark=fmark))
    f_ref = {f.id: f.ref for f in f_items}

    # Test cases as a tree: siblings by (category, title), depth-first.
    testcases = list(testcases or [])
    id_set = {t.id for t in testcases}
    kids: dict = {}
    for t in testcases:
        parent = getattr(t, 'parent_id', None)
        kids.setdefault(parent if parent in id_set else None, []).append(t)
    for lst in kids.values():
        lst.sort(key=lambda t: (_v(t.category), (t.title or '')))
    walk: list = []

    def _walk(parent, prefix, depth):
        for i, t in enumerate(kids.get(parent, []), 1):
            num = f'{prefix}{i}'
            walk.append((t, num, depth))
            _walk(t.id, num + '.', depth + 1)
    _walk(None, '', 0)
    t_ref = {t.id: f'T{i}' for i, (t, _n, _d) in enumerate(walk, 1)}

    t_items = []
    for t, num, depth in walk:
        parent = getattr(t, 'parent_id', None)
        t_items.append(TestcaseItem(
            src=t, id=t.id, ref=t_ref[t.id], number=num, depth=depth,
            parent_ref=t_ref.get(parent), title=t.title or 'Untitled',
            category=_title_case(t.category), status=testcase_status(t),
            fields=_fields(t, _TESTCASE_FIELDS),
            assets=[a.name for a in (getattr(t, 'assets', None) or [])],
            findings=[LinkedFinding(f_ref.get(x.id), x.title or 'Untitled', _v(x.severity).upper())
                      for x in (getattr(t, 'findings', None) or [])],
            mark=mk.of(t)))

    c_items = []
    for ca in (cleanup_artifacts or []):
        c_items.append(CleanupItem(
            src=ca, id=getattr(ca, 'id', None), title=ca.title or 'Artifact',
            artifact_type=_title_case(ca.artifact_type), status=_title_case(ca.status) or 'Pending',
            location=ca.location or '', fields=_fields(ca, _CLEANUP_FIELDS),
            assets=[a.name for a in (getattr(ca, 'assets', None) or [])],
            finding_refs=[f_ref[x.id] for x in (getattr(ca, 'findings', None) or []) if x.id in f_ref],
            mark=mk.of(ca)))

    s_items = []
    for s in (sections or []):
        smark = mk.of(s)
        explicit = bool(getattr(s, 'classification_level', None))
        s_items.append(SectionBlock(
            src=s, kind=_v(s.section_type).upper(), title=s.title or '',
            content=getattr(s, 'content', None) or '',
            heading_mark=smark if explicit else structural, mark=smark,
            page_break_before=bool(getattr(s, 'page_break_before', False))))

    # Banner: the high-water mark of every portion in the document.
    banner = None
    if engine:
        levels = [getattr(engagement, 'default_classification_level', None)]
        levels += [s.mark.level for s in s_items]
        for f in f_items:
            levels.append(f.mark.level)
            levels += [e.mark.level for e in f.evidence]
        levels += [t.mark.level for t in t_items]
        levels += [c.mark.level for c in c_items]
        top = engine.highest(levels)
        b = engine.banner(top) if top else None
        if b:
            banner = Banner(top, *b)

    counts = {s: 0 for s in SEVERITY_ORDER}
    for f in f_items:
        counts[f.severity] = counts.get(f.severity, 0) + 1

    title = (getattr(theme, 'cover_title', None) if theme else None) or default_title
    return ReportDocument(
        engagement=engagement, title=title, client=getattr(engagement, 'client_name', None) or '',
        engagement_name=getattr(engagement, 'name', None) or '', generated_on=date.today(),
        marking=engine, sections=s_items, findings=f_items, testcases=t_items, cleanup=c_items,
        banner=banner, structural_mark=structural, default_mark=mk.mark(None, None),
        severity_counts=counts)
