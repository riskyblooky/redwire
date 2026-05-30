"""
search.py — Advanced Global Search

Supports a rich query language:

  bare terms          'SSRF vuln'           full-text AND across all resources
  quoted phrases      '"SQL injection"'     exact phrase match
  boolean ops         'SSRF AND severity:HIGH'
                      'XSS OR CSRF'
                      'SSRF NOT remediated'
  grouping            'status:open AND (severity:critical OR severity:high)'
  category dorks      'finding:SSRF'        scope to a resource category
  field dorks         'severity:HIGH'       filter specific model column
                      'status:OPEN'
                      'type:web'
                      'cat:injection'
                      'engagement:acme'
                      'client:corp'

Grammar (informal):
  query   = clause (OP clause)*
  clause  = NOT? (group | dork | term)
  group   = '(' query ')'
  dork    = FIELD ':' value
  value   = QUOTED | WORD
  term    = QUOTED | WORD
  OP      = AND | OR   (implicit AND when nothing between terms)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, cast, func, not_, or_, select, String
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from auth.rbac import check_engagement_permission
from models.permission import Permission
from database import get_db
from models.asset import Asset
from models.associations import EngagementAssignment
from models.client import Client
from models.engagement import Engagement
from models.finding import Finding
from models.testcase import TestCase
from models.user import User, UserRole
from models.vault import VaultItem

router = APIRouter(prefix="/search", tags=["search"])


# ── helpers ─────────────────────────────────────────────────────────────


def _snippet(text: str | None, max_len: int = 300) -> str:
    if not text:
        return ""
    text = text.strip()
    return text[:max_len] + "…" if len(text) > max_len else text


# ── tokenizer ───────────────────────────────────────────────────────────

# All recognized dork fields and the category scoping keywords
_CATEGORY_FIELDS = {"finding", "asset", "testcase", "engagement", "client", "vault"}
_FIELD_DORKS = {"severity", "status", "type", "cat", "engagement", "client"}
# combined for regex
_ALL_FIELDS = _CATEGORY_FIELDS | _FIELD_DORKS

_TOKEN_RE = re.compile(
    r'(?i)'
    r'(?P<LPAREN>\()'
    r'|(?P<RPAREN>\))'
    r'|(?P<AND>\bAND\b)'
    r'|(?P<OR>\bOR\b)'
    r'|(?P<NOT>\bNOT\b)'
    r'|(?P<DORK>(?:' + '|'.join(sorted(_ALL_FIELDS, key=len, reverse=True)) + r'):(?:"[^"]*"|\S+))'
    r'|(?P<QUOTED>"[^"]*")'
    r'|(?P<WORD>\S+)'
)


@dataclass
class Token:
    kind: str   # LPAREN RPAREN AND OR NOT DORK QUOTED WORD
    value: str


def tokenize(query: str) -> List[Token]:
    tokens: List[Token] = []
    for m in _TOKEN_RE.finditer(query):
        kind = m.lastgroup
        tokens.append(Token(kind=kind, value=m.group()))
    return tokens


# ── AST nodes ───────────────────────────────────────────────────────────

@dataclass
class TextNode:
    term: str       # already lowercased, quotes stripped

@dataclass
class FieldNode:
    field: str      # severity / status / type / cat / engagement / client
    value: str      # lowercased

@dataclass
class CategoryNode:
    category: str   # finding / asset / testcase / vault / client / engagement
    term: str       # the search term within that category

@dataclass
class AndNode:
    children: List[Any]

@dataclass
class OrNode:
    children: List[Any]

@dataclass
class NotNode:
    child: Any


# ── parser ──────────────────────────────────────────────────────────────

class Parser:
    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.pos = 0

    def peek(self) -> Optional[Token]:
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def consume(self, kind: Optional[str] = None) -> Token:
        tok = self.tokens[self.pos]
        if kind and tok.kind != kind:
            raise ValueError(f"Expected {kind}, got {tok.kind!r}: {tok.value!r}")
        self.pos += 1
        return tok

    def at_end(self) -> bool:
        return self.pos >= len(self.tokens)

    def parse(self) -> Any:
        return self._parse_or()

    def _parse_or(self) -> Any:
        left = self._parse_and()
        while self.peek() and self.peek().kind == "OR":
            self.consume("OR")
            right = self._parse_and()
            if isinstance(left, OrNode):
                left.children.append(right)
            else:
                left = OrNode(children=[left, right])
        return left

    def _parse_and(self) -> Any:
        left = self._parse_not()
        while self.peek() and self.peek().kind not in ("OR", "RPAREN") and not self.at_end():
            # explicit AND or implicit (two consecutive non-OR tokens)
            if self.peek().kind == "AND":
                self.consume("AND")
            elif self.peek().kind in ("OR", "RPAREN"):
                break
            else:
                pass  # implicit AND
            right = self._parse_not()
            if isinstance(left, AndNode):
                left.children.append(right)
            else:
                left = AndNode(children=[left, right])
        return left

    def _parse_not(self) -> Any:
        if self.peek() and self.peek().kind == "NOT":
            self.consume("NOT")
            child = self._parse_atom()
            return NotNode(child=child)
        return self._parse_atom()

    def _parse_atom(self) -> Any:
        tok = self.peek()
        if tok is None:
            raise ValueError("Unexpected end of query")

        if tok.kind == "LPAREN":
            self.consume("LPAREN")
            node = self._parse_or()
            if self.peek() and self.peek().kind == "RPAREN":
                self.consume("RPAREN")
            return node

        if tok.kind == "DORK":
            self.consume("DORK")
            # split on first ':'
            colon_idx = tok.value.index(":")
            raw_field = tok.value[:colon_idx].lower()
            raw_value = tok.value[colon_idx + 1:].strip('"').lower()
            if raw_field in _CATEGORY_FIELDS:
                return CategoryNode(category=raw_field, term=raw_value)
            return FieldNode(field=raw_field, value=raw_value)

        if tok.kind == "QUOTED":
            self.consume("QUOTED")
            return TextNode(term=tok.value.strip('"').lower())

        if tok.kind == "WORD":
            self.consume("WORD")
            return TextNode(term=tok.value.lower())

        # skip unknowns
        self.consume()
        return TextNode(term="")


def parse_query(q: str) -> Any:
    """Parse a search query string into an AST."""
    q = q.strip()
    if not q:
        return None
    try:
        tokens = tokenize(q)
        if not tokens:
            return None
        return Parser(tokens).parse()
    except Exception:
        # Fallback: treat entire query as a bare text search
        return TextNode(term=q.lower())


def extract_category_scope(node: Any) -> Tuple[Optional[str], Any]:
    """If the top-level node is a single CategoryNode, return (category, TextNode(term)).
    Otherwise return (None, node)."""
    if isinstance(node, CategoryNode):
        return node.category, TextNode(term=node.term)
    return None, node


# ── SQLAlchemy clause builder ────────────────────────────────────────────

def _like(col, term: str):
    """Case-insensitive LIKE on a column for a term."""
    return col.ilike(f"%{term}%")


def build_finding_clause(node: Any):
    """Walk AST and produce a SQLAlchemy boolean expression for Finding."""
    if node is None:
        return None
    if isinstance(node, TextNode):
        if not node.term:
            return None
        return or_(
            Finding.title.ilike(f"%{node.term}%"),
            Finding.category.ilike(f"%{node.term}%"),
            Finding.description.ilike(f"%{node.term}%"),
            Finding.impact.ilike(f"%{node.term}%"),
            Finding.technical_details.ilike(f"%{node.term}%"),
        )
    if isinstance(node, FieldNode):
        if node.field == "severity":
            return func.lower(cast(Finding.severity, String)) == node.value.lower()
        if node.field == "status":
            return func.lower(cast(Finding.status, String)) == node.value.lower()
        if node.field == "cat":
            return Finding.category.ilike(f"%{node.value}%")
        if node.field == "engagement":
            return Engagement.name.ilike(f"%{node.value}%")
        if node.field == "client":
            return Engagement.client_name.ilike(f"%{node.value}%")
        # type / other fields → broad text match
        return or_(
            Finding.title.ilike(f"%{node.value}%"),
            Finding.description.ilike(f"%{node.value}%"),
        )
    if isinstance(node, CategoryNode):
        if node.category == "finding":
            return build_finding_clause(TextNode(term=node.term))
        return None  # other category nodes ignored for findings
    if isinstance(node, AndNode):
        clauses = [c for c in (build_finding_clause(ch) for ch in node.children) if c is not None]
        return and_(*clauses) if clauses else None
    if isinstance(node, OrNode):
        clauses = [c for c in (build_finding_clause(ch) for ch in node.children) if c is not None]
        return or_(*clauses) if clauses else None
    if isinstance(node, NotNode):
        inner = build_finding_clause(node.child)
        return not_(inner) if inner is not None else None
    return None


def build_asset_clause(node: Any):
    if node is None:
        return None
    if isinstance(node, TextNode):
        if not node.term:
            return None
        return or_(
            Asset.name.ilike(f"%{node.term}%"),
            Asset.identifier.ilike(f"%{node.term}%"),
            Asset.description.ilike(f"%{node.term}%"),
            Asset.notes.ilike(f"%{node.term}%"),
        )
    if isinstance(node, FieldNode):
        if node.field == "type":
            return Asset.asset_type.ilike(f"%{node.value}%")
        if node.field == "engagement":
            return Engagement.name.ilike(f"%{node.value}%")
        if node.field == "client":
            return Engagement.client_name.ilike(f"%{node.value}%")
        return or_(
            Asset.name.ilike(f"%{node.value}%"),
            Asset.identifier.ilike(f"%{node.value}%"),
        )
    if isinstance(node, CategoryNode):
        if node.category == "asset":
            return build_asset_clause(TextNode(term=node.term))
        return None
    if isinstance(node, AndNode):
        clauses = [c for c in (build_asset_clause(ch) for ch in node.children) if c is not None]
        return and_(*clauses) if clauses else None
    if isinstance(node, OrNode):
        clauses = [c for c in (build_asset_clause(ch) for ch in node.children) if c is not None]
        return or_(*clauses) if clauses else None
    if isinstance(node, NotNode):
        inner = build_asset_clause(node.child)
        return not_(inner) if inner is not None else None
    return None


def build_engagement_clause(node: Any):
    if node is None:
        return None
    if isinstance(node, TextNode):
        if not node.term:
            return None
        return or_(
            Engagement.name.ilike(f"%{node.term}%"),
            Engagement.client_name.ilike(f"%{node.term}%"),
            Engagement.description.ilike(f"%{node.term}%"),
        )
    if isinstance(node, FieldNode):
        if node.field == "type":
            return Engagement.engagement_type.ilike(f"%{node.value}%")
        if node.field == "status":
            return func.lower(cast(Engagement.status, String)) == node.value.lower()
        if node.field == "engagement":
            return Engagement.name.ilike(f"%{node.value}%")
        if node.field == "client":
            return Engagement.client_name.ilike(f"%{node.value}%")
        return Engagement.name.ilike(f"%{node.value}%")
    if isinstance(node, CategoryNode):
        if node.category == "engagement":
            return build_engagement_clause(TextNode(term=node.term))
        return None
    if isinstance(node, AndNode):
        clauses = [c for c in (build_engagement_clause(ch) for ch in node.children) if c is not None]
        return and_(*clauses) if clauses else None
    if isinstance(node, OrNode):
        clauses = [c for c in (build_engagement_clause(ch) for ch in node.children) if c is not None]
        return or_(*clauses) if clauses else None
    if isinstance(node, NotNode):
        inner = build_engagement_clause(node.child)
        return not_(inner) if inner is not None else None
    return None


def build_testcase_clause(node: Any):
    if node is None:
        return None
    if isinstance(node, TextNode):
        if not node.term:
            return None
        return or_(
            TestCase.title.ilike(f"%{node.term}%"),
            TestCase.category.ilike(f"%{node.term}%"),
            TestCase.description.ilike(f"%{node.term}%"),
        )
    if isinstance(node, FieldNode):
        if node.field == "cat":
            return TestCase.category.ilike(f"%{node.value}%")
        if node.field == "engagement":
            return Engagement.name.ilike(f"%{node.value}%")
        return TestCase.title.ilike(f"%{node.value}%")
    if isinstance(node, CategoryNode):
        if node.category == "testcase":
            return build_testcase_clause(TextNode(term=node.term))
        return None
    if isinstance(node, AndNode):
        clauses = [c for c in (build_testcase_clause(ch) for ch in node.children) if c is not None]
        return and_(*clauses) if clauses else None
    if isinstance(node, OrNode):
        clauses = [c for c in (build_testcase_clause(ch) for ch in node.children) if c is not None]
        return or_(*clauses) if clauses else None
    if isinstance(node, NotNode):
        inner = build_testcase_clause(node.child)
        return not_(inner) if inner is not None else None
    return None


def build_client_clause(node: Any):
    if node is None:
        return None
    if isinstance(node, TextNode):
        if not node.term:
            return None
        return or_(
            Client.name.ilike(f"%{node.term}%"),
            Client.contact_name.ilike(f"%{node.term}%"),
            Client.contact_email.ilike(f"%{node.term}%"),
            Client.description.ilike(f"%{node.term}%"),
        )
    if isinstance(node, FieldNode):
        if node.field == "client":
            return Client.name.ilike(f"%{node.value}%")
        return Client.name.ilike(f"%{node.value}%")
    if isinstance(node, CategoryNode):
        if node.category == "client":
            return build_client_clause(TextNode(term=node.term))
        return None
    if isinstance(node, AndNode):
        clauses = [c for c in (build_client_clause(ch) for ch in node.children) if c is not None]
        return and_(*clauses) if clauses else None
    if isinstance(node, OrNode):
        clauses = [c for c in (build_client_clause(ch) for ch in node.children) if c is not None]
        return or_(*clauses) if clauses else None
    if isinstance(node, NotNode):
        inner = build_client_clause(node.child)
        return not_(inner) if inner is not None else None
    return None


def build_vault_clause(node: Any):
    if node is None:
        return None
    if isinstance(node, TextNode):
        if not node.term:
            return None
        return or_(
            VaultItem.name.ilike(f"%{node.term}%"),
            VaultItem.item_type.ilike(f"%{node.term}%"),
            VaultItem.description.ilike(f"%{node.term}%"),
        )
    if isinstance(node, FieldNode):
        if node.field == "type":
            return VaultItem.item_type.ilike(f"%{node.value}%")
        return VaultItem.name.ilike(f"%{node.value}%")
    if isinstance(node, CategoryNode):
        if node.category == "vault":
            return build_vault_clause(TextNode(term=node.term))
        return None
    if isinstance(node, AndNode):
        clauses = [c for c in (build_vault_clause(ch) for ch in node.children) if c is not None]
        return and_(*clauses) if clauses else None
    if isinstance(node, OrNode):
        clauses = [c for c in (build_vault_clause(ch) for ch in node.children) if c is not None]
        return or_(*clauses) if clauses else None
    if isinstance(node, NotNode):
        inner = build_vault_clause(node.child)
        return not_(inner) if inner is not None else None
    return None


def _has_category_node(node: Any, category: str) -> bool:
    """Return True if this AST exclusively scopes to a specific category."""
    if isinstance(node, CategoryNode):
        return node.category == category
    return False


def _should_search_category(node: Any, category: str) -> bool:
    """Should we search this resource category given the query?

    We skip a category if the query contains a CategoryNode for a DIFFERENT category,
    but include it if the query has no category constraints or explicitly scopes to it.
    """
    # collect all CategoryNode categories in the AST
    cats = set()
    _collect_categories(node, cats)
    if not cats:
        return True  # no category filtering
    return category in cats


def _collect_categories(node: Any, result: set):
    if isinstance(node, CategoryNode):
        result.add(node.category)
    elif isinstance(node, (AndNode, OrNode)):
        for ch in node.children:
            _collect_categories(ch, result)
    elif isinstance(node, NotNode):
        _collect_categories(node.child, result)


# ── match count helper ───────────────────────────────────────────────────

def _count_matches(fields: dict, terms: List[str]) -> int:
    """Count how many field values contain at least one of the search terms."""
    count = 0
    for val in fields.values():
        if val and any(t in val.lower() for t in terms if t):
            count += 1
    return count


def _extract_text_terms(node: Any) -> List[str]:
    """Collect all TextNode terms from the AST for highlight/match counting."""
    terms = []
    if isinstance(node, TextNode):
        if node.term:
            terms.append(node.term)
    elif isinstance(node, FieldNode):
        terms.append(node.value)
    elif isinstance(node, CategoryNode):
        if node.term:
            terms.append(node.term)
    elif isinstance(node, (AndNode, OrNode)):
        for ch in node.children:
            terms.extend(_extract_text_terms(ch))
    elif isinstance(node, NotNode):
        pass  # don't highlight NOT terms
    return terms


# ── permission helper ────────────────────────────────────────────────────

async def _get_accessible_engagement_ids(user: User, db: AsyncSession) -> Optional[List[str]]:
    if user.role in [UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD]:
        return None
    result = await db.execute(
        select(EngagementAssignment.engagement_id)
        .where(EngagementAssignment.user_id == user.id)
    )
    return [row[0] for row in result.all()]


# ── endpoint ─────────────────────────────────────────────────────────────

@router.get("")
async def global_search(
    q: str = Query(..., min_length=1, description=(
        "Boolean search query. Supports: AND, OR, NOT, parentheses, "
        "quoted phrases, field dorks (severity:HIGH, status:OPEN, type:web, "
        "cat:injection, engagement:name, client:name), "
        "and category scoping (finding:, asset:, testcase:, engagement:, client:, vault:)"
    )),
    limit: int = Query(8, ge=1, le=50, description="Max results per category"),
    sort: str = Query("relevance", description="Sort order: relevance | updated"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Advanced boolean search across all accessible resources."""
    ast = parse_query(q)
    text_terms = _extract_text_terms(ast) if ast else []
    accessible_ids = await _get_accessible_engagement_ids(current_user, db)

    def scope_to_engagements(query, engagement_col):
        if accessible_ids is not None:
            return query.where(engagement_col.in_(accessible_ids))
        return query

    results = []

    # ── Engagements ──────────────────────────────────────────────────────
    if _should_search_category(ast, "engagement"):
        clause = build_engagement_clause(ast) if ast else None
        eng_q = select(
            Engagement.id, Engagement.name, Engagement.client_name,
            Engagement.status, Engagement.engagement_type, Engagement.description,
            Engagement.scope,
        )
        if clause is not None:
            eng_q = eng_q.where(clause)
        if accessible_ids is not None:
            eng_q = eng_q.where(Engagement.id.in_(accessible_ids))
        if sort == "relevance":
            eng_q = eng_q.order_by(Engagement.updated_at.desc())
        else:
            eng_q = eng_q.order_by(Engagement.updated_at.desc())
        eng_q = eng_q.limit(limit)
        rows = (await db.execute(eng_q)).all()
        items = []
        for row in rows:
            fields = {
                "Name": row.name or "",
                "Client": row.client_name or "",
                "Description": _snippet(row.description),
                "Scope": _snippet(row.scope, 200),
            }
            items.append({
                "id": row.id,
                "title": row.name,
                "subtitle": f"{row.client_name} · {row.engagement_type}",
                "status": row.status.value if row.status else None,
                "description": _snippet(row.description),
                "fields": fields,
                "url": f"/engagements/{row.id}",
                "match_count": _count_matches(fields, text_terms),
            })
        if sort == "relevance":
            items.sort(key=lambda x: x["match_count"], reverse=True)
        if items:
            results.append({"category": "engagements", "items": items})

    # ── Findings ─────────────────────────────────────────────────────────
    if _should_search_category(ast, "finding"):
        clause = build_finding_clause(ast) if ast else None
        find_q = select(
            Finding.id, Finding.title, Finding.category, Finding.severity,
            Finding.status, Finding.engagement_id,
            Engagement.name.label("engagement_name"), Engagement.client_name,
            Finding.description, Finding.impact,
        ).join(Engagement, Finding.engagement_id == Engagement.id)
        if clause is not None:
            find_q = find_q.where(clause)
        find_q = scope_to_engagements(find_q, Finding.engagement_id)
        find_q = find_q.order_by(Finding.updated_at.desc()).limit(limit)
        rows = (await db.execute(find_q)).all()
        items = []
        for row in rows:
            fields = {
                "Title": row.title or "",
                "Category": row.category or "",
                "Description": _snippet(row.description),
                "Impact": _snippet(row.impact, 200),
                "Engagement": row.engagement_name or "",
            }
            items.append({
                "id": row.id,
                "title": row.title,
                "subtitle": f"{row.severity.value if row.severity else ''} · {row.category or 'Uncategorized'}",
                "status": row.status.value if row.status else None,
                "description": _snippet(row.description),
                "fields": fields,
                "engagement_name": row.engagement_name,
                "url": f"/findings/{row.id}?engagementId={row.engagement_id}",
                "match_count": _count_matches(fields, text_terms),
            })
        if sort == "relevance":
            items.sort(key=lambda x: x["match_count"], reverse=True)
        if items:
            results.append({"category": "findings", "items": items})

    # ── Assets ───────────────────────────────────────────────────────────
    if _should_search_category(ast, "asset"):
        clause = build_asset_clause(ast) if ast else None
        asset_q = select(
            Asset.id, Asset.name, Asset.identifier, Asset.asset_type,
            Asset.engagement_id, Engagement.name.label("engagement_name"),
            Asset.description, Asset.notes,
        ).join(Engagement, Asset.engagement_id == Engagement.id)
        if clause is not None:
            asset_q = asset_q.where(clause)
        asset_q = scope_to_engagements(asset_q, Asset.engagement_id)
        asset_q = asset_q.order_by(Asset.updated_at.desc()).limit(limit)
        rows = (await db.execute(asset_q)).all()
        items = []
        for row in rows:
            fields = {
                "Name": row.name or "",
                "Identifier": row.identifier or "",
                "Type": row.asset_type or "",
                "Description": _snippet(row.description),
                "Notes": _snippet(row.notes, 200),
            }
            items.append({
                "id": row.id,
                "title": row.name,
                "subtitle": f"{row.identifier} · {row.asset_type}",
                "description": _snippet(row.description),
                "fields": fields,
                "engagement_name": row.engagement_name,
                "url": f"/assets/{row.id}",
                "match_count": _count_matches(fields, text_terms),
            })
        if sort == "relevance":
            items.sort(key=lambda x: x["match_count"], reverse=True)
        if items:
            results.append({"category": "assets", "items": items})

    # ── Test Cases ───────────────────────────────────────────────────────
    if _should_search_category(ast, "testcase"):
        clause = build_testcase_clause(ast) if ast else None
        tc_q = select(
            TestCase.id, TestCase.title, TestCase.category,
            TestCase.is_executed, TestCase.is_successful,
            TestCase.engagement_id, Engagement.name.label("engagement_name"),
            TestCase.description,
        ).join(Engagement, TestCase.engagement_id == Engagement.id)
        if clause is not None:
            tc_q = tc_q.where(clause)
        tc_q = scope_to_engagements(tc_q, TestCase.engagement_id)
        tc_q = tc_q.order_by(TestCase.updated_at.desc()).limit(limit)
        rows = (await db.execute(tc_q)).all()
        items = []
        for row in rows:
            status_label = "Not Executed"
            if row.is_executed:
                status_label = "Pass" if row.is_successful else "Fail"
            fields = {
                "Title": row.title or "",
                "Category": row.category or "",
                "Description": _snippet(row.description),
            }
            items.append({
                "id": row.id,
                "title": row.title,
                "subtitle": f"{row.category} · {status_label}",
                "description": _snippet(row.description),
                "fields": fields,
                "engagement_name": row.engagement_name,
                "url": f"/engagements/{row.engagement_id}?tab=testcases",
                "match_count": _count_matches(fields, text_terms),
            })
        if sort == "relevance":
            items.sort(key=lambda x: x["match_count"], reverse=True)
        if items:
            results.append({"category": "testcases", "items": items})

    # ── Clients ──────────────────────────────────────────────────────────
    if _should_search_category(ast, "client"):
        clause = build_client_clause(ast) if ast else None
        client_q = select(
            Client.id, Client.name, Client.contact_name,
            Client.contact_email, Client.description,
        )
        if clause is not None:
            client_q = client_q.where(clause)
        # GHSA-h52c-fq68-j82x: confine non-admins to clients reachable through
        # the engagements they're assigned to.
        if accessible_ids is not None:
            client_q = client_q.where(
                Client.id.in_(
                    select(Engagement.client_id).where(Engagement.id.in_(accessible_ids))
                )
            )
        client_q = client_q.order_by(Client.name).limit(limit)
        rows = (await db.execute(client_q)).all()
        items = []
        for row in rows:
            subtitle_parts = [p for p in [row.contact_name, row.contact_email] if p]
            fields = {
                "Name": row.name or "",
                "Contact": row.contact_name or "",
                "Email": row.contact_email or "",
                "Description": _snippet(row.description),
            }
            items.append({
                "id": row.id,
                "title": row.name,
                "subtitle": " · ".join(subtitle_parts) if subtitle_parts else "No contact info",
                "description": _snippet(row.description),
                "fields": fields,
                "url": f"/clients",
                "match_count": _count_matches(fields, text_terms),
            })
        if sort == "relevance":
            items.sort(key=lambda x: x["match_count"], reverse=True)
        if items:
            results.append({"category": "clients", "items": items})

    # ── Vault ────────────────────────────────────────────────────────────
    # GHSA-h52c-fq68-j82x: reduce non-admin scope to engagements where the
    # caller actually holds VAULT_VIEW (engagement membership alone is not
    # sufficient — the dedicated vault router enforces this).
    vault_eids = accessible_ids
    if vault_eids is not None:
        vault_eids = [
            eid for eid in vault_eids
            if await check_engagement_permission(
                current_user.id, eid, Permission.VAULT_VIEW.value, db)
        ]
    if _should_search_category(ast, "vault") and (vault_eids is None or vault_eids):
        clause = build_vault_clause(ast) if ast else None
        vault_q = select(
            VaultItem.id, VaultItem.name, VaultItem.item_type,
            VaultItem.engagement_id, Engagement.name.label("engagement_name"),
            VaultItem.description,
        ).join(Engagement, VaultItem.engagement_id == Engagement.id)
        if clause is not None:
            vault_q = vault_q.where(clause)
        if vault_eids is not None:
            vault_q = vault_q.where(VaultItem.engagement_id.in_(vault_eids))
        vault_q = vault_q.limit(limit)
        rows = (await db.execute(vault_q)).all()
        items = []
        for row in rows:
            fields = {
                "Name": row.name or "",
                "Type": row.item_type or "",
                "Description": _snippet(row.description),
            }
            items.append({
                "id": row.id,
                "title": row.name,
                "subtitle": row.item_type,
                "description": _snippet(row.description),
                "fields": fields,
                "engagement_name": row.engagement_name,
                "url": f"/engagements/{row.engagement_id}?tab=vault",
                "match_count": _count_matches(fields, text_terms),
            })
        if sort == "relevance":
            items.sort(key=lambda x: x["match_count"], reverse=True)
        if items:
            results.append({"category": "vault", "items": items})

    return {
        "query": q,
        "parsed_terms": text_terms,
        "results": results,
        "total": sum(len(cat["items"]) for cat in results),
    }
