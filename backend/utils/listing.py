"""One contract for list endpoints: paging, total count, ranked text search
and sorting.

- Paging: ``skip`` (``offset`` accepted as an alias) and ``limit``. Lists
  that returned everything before keep doing so when no ``limit`` is sent
  (paging is opt-in there); already-paged lists keep their default.
- Total: the number of rows matching the filters, ignoring paging, in the
  ``X-Total-Count`` header (CORS exposes it). Response bodies don't change.
- Search: ``q`` (``search`` accepted as an alias) matches any of the
  searchable columns, and ranks hits so a whole match never sits below a
  partial one: the whole field equal to the term, then the term as whole
  words ("domain" in "domain admin"), then as a word prefix ("domain" in
  "domains"), then inside a word ("domain" in "subdomain"). Earlier columns
  win ties (a title hit above a description hit). This is the ordering the
  list pages used to compute in the browser over a full download.
- Sort: ``sort_by`` from the endpoint's allow-list (anything else is a 422
  naming the allowed values) and ``sort_order`` (``sort_dir`` accepted).
  While searching, rank comes first and the sort orders within a rank. The
  primary key is always the last key, so pages never repeat or drop rows.

Every value reaches SQL as a bound parameter.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping, Optional, Sequence

from fastapi import HTTPException, Query, Response, status
from sqlalchemy import Select, case, func, literal, or_, select
from sqlalchemy.sql.elements import ColumnElement

from schemas._field_limits import MAX_LIST_LIMIT

MAX_QUERY_LENGTH = 200


@dataclass
class ListParams:
    skip: int
    limit: Optional[int]
    q: Optional[str]
    sort_by: Optional[str]
    descending: Optional[bool]  # None = the endpoint's default direction


def list_params(default_limit: Optional[int] = None, max_limit: int = MAX_LIST_LIMIT):
    """FastAPI dependency factory. ``default_limit=None`` means "everything
    when the caller sends no limit" (the opt-in lists)."""

    def _dep(
        skip: Optional[int] = Query(None, ge=0, description="Rows to skip."),
        offset: Optional[int] = Query(None, ge=0, description="Alias of skip."),
        limit: Optional[int] = Query(default_limit, ge=1, le=max_limit,
                                     description="Page size; the total is in X-Total-Count."),
        q: Optional[str] = Query(None, max_length=MAX_QUERY_LENGTH, description="Ranked text search."),
        search: Optional[str] = Query(None, max_length=MAX_QUERY_LENGTH, description="Alias of q."),
        sort_by: Optional[str] = Query(None, max_length=64),
        sort_order: Optional[str] = Query(None, pattern="^(asc|desc)$"),
        sort_dir: Optional[str] = Query(None, pattern="^(asc|desc)$", description="Alias of sort_order."),
    ) -> ListParams:
        term = (q if q is not None else search) or ""
        order = sort_order or sort_dir
        return ListParams(
            skip=skip if skip is not None else (offset or 0),
            limit=limit,
            q=term.strip() or None,
            sort_by=sort_by or None,
            descending=None if order is None else order == "desc",
        )

    return _dep


# ── search ──────────────────────────────────────────────────────────────

def _like_escape(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _regex_escape(term: str) -> str:
    # Postgres ARE: a backslash before a non-alphanumeric is that literal
    # character, so escaping every one of them leaves no metacharacters.
    return re.sub(r"([^0-9A-Za-z])", r"\\\1", term)


def search_clause(term: str, columns: Sequence[ColumnElement]) -> ColumnElement:
    """Rows where any searchable column contains ``term`` (case-insensitive)."""
    pattern = f"%{_like_escape(term)}%"
    return or_(*(col.ilike(pattern, escape="\\") for col in columns))


def search_rank(term: str, columns: Sequence[ColumnElement]) -> ColumnElement:
    """Lower is better: tier (exact, whole word, word prefix, substring) first,
    then the column's position. Rows matching nowhere get the worst rank."""
    word = _regex_escape(term)
    whole, prefix = f"\\m{word}\\M", f"\\m{word}"
    contains = f"%{_like_escape(term)}%"
    n = len(columns)
    ranks = []
    for i, col in enumerate(columns):
        ranks.append(case(
            (func.lower(col) == term.lower(), literal(0 * n + i)),
            (col.op("~*")(whole), literal(1 * n + i)),
            (col.op("~*")(prefix), literal(2 * n + i)),
            (col.ilike(contains, escape="\\"), literal(3 * n + i)),
            else_=literal(4 * n),
        ))
    return ranks[0] if n == 1 else func.least(*ranks)


# ── sort ────────────────────────────────────────────────────────────────

def order_keys(params: ListParams, sortable: Mapping[str, ColumnElement], *,
               default: str, default_descending: bool, pk: ColumnElement,
               rank: Optional[ColumnElement] = None) -> list:
    """ORDER BY keys: rank (when searching), the chosen sort, then the pk."""
    name = params.sort_by or default
    if name not in sortable:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"sort_by must be one of: {', '.join(sorted(sortable))}",
        )
    descending = default_descending if params.descending is None else params.descending
    col = sortable[name]
    keys = [rank] if rank is not None else []
    keys.append(col.desc().nulls_last() if descending else col.asc().nulls_last())
    keys.append(pk.desc() if descending else pk.asc())
    return keys


# ── paging ──────────────────────────────────────────────────────────────

async def count_and_page(db, response: Response, query: Select, params: ListParams, *,
                         count_from, filters: Sequence[ColumnElement], order: list) -> list:
    """Set X-Total-Count to the rows of ``count_from`` matching ``filters``,
    then run ``query`` ordered and paged. ``count_from`` is the base entity
    (the list query itself may join and group for display columns)."""
    total = (await db.execute(
        select(func.count()).select_from(count_from).where(*filters)
    )).scalar_one()
    set_total(response, total)
    query = query.order_by(*order).offset(params.skip)
    if params.limit is not None:
        query = query.limit(params.limit)
    return (await db.execute(query)).all()


def set_total(response: Response, total: int) -> None:
    response.headers["X-Total-Count"] = str(total)
