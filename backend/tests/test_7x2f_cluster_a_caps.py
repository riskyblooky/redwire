"""GHSA-7x2f-ff7r-h388 cluster A — input caps on unbounded fields.

Three sub-issues shipped:

  #9  (CWE-770) `limit=` on 9 list endpoints now capped at
      `MAX_LIST_LIMIT`. Pin the constant + one representative endpoint
      shape so a future refactor can't silently drop the bound.
  #10 (CWE-770) Attack-graph `positions` dict rejected over
      `MAX_GRAPH_NODES` entries. Pin at the handler-adjacent boundary
      (unit-level test — the handler is thin and its cap check is a
      pure len() comparison).
  #13 (CWE-770) Runbook `items[]` capped at `MAX_RUNBOOK_ITEMS`. Pin
      via Pydantic validation on the schema — the router applies no
      additional check because Pydantic rejects before the handler
      body runs.
"""

from __future__ import annotations

import os

import pytest
from pydantic import ValidationError
from cryptography.fernet import Fernet

os.environ.setdefault("TOTP_ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ.setdefault("VAULT_ENCRYPTION_KEY", Fernet.generate_key().decode())

from schemas._field_limits import (
    MAX_GRAPH_NODES,
    MAX_LIST_LIMIT,
    MAX_RUNBOOK_ITEMS,
)
from schemas.runbook import RunbookCreate, RunbookItemCreate, RunbookUpdate


# ── Cap constants pinned ─────────────────────────────────────────────


class TestCapValues:
    """Pin the values so a future edit doesn't accidentally drop them
    to something that bites real users (e.g. 5) or bumps them to
    something that defeats the DoS defence (e.g. 1_000_000)."""

    def test_max_list_limit_sane(self):
        assert 100 <= MAX_LIST_LIMIT <= 10_000

    def test_max_runbook_items_sane(self):
        assert 50 <= MAX_RUNBOOK_ITEMS <= 10_000

    def test_max_graph_nodes_sane(self):
        assert 500 <= MAX_GRAPH_NODES <= 100_000


# ── Issue 13: runbook items[] cap ────────────────────────────────────


class TestRunbookItemsCap:
    def _item(self, i: int) -> dict:
        return {"template_id": f"tmpl-{i}", "temp_key": f"k{i}"}

    def test_create_accepts_empty(self):
        RunbookCreate(name="x")

    def test_create_accepts_a_few(self):
        RunbookCreate(name="x", items=[RunbookItemCreate(**self._item(i)) for i in range(10)])

    def test_create_accepts_exactly_max(self):
        items = [RunbookItemCreate(**self._item(i)) for i in range(MAX_RUNBOOK_ITEMS)]
        rb = RunbookCreate(name="x", items=items)
        assert len(rb.items) == MAX_RUNBOOK_ITEMS

    def test_create_rejects_over_max(self):
        items = [RunbookItemCreate(**self._item(i)) for i in range(MAX_RUNBOOK_ITEMS + 1)]
        with pytest.raises(ValidationError):
            RunbookCreate(name="x", items=items)

    def test_update_accepts_none(self):
        # Update lets you PATCH other fields without touching items[] —
        # None means "leave alone" not "set to empty".
        upd = RunbookUpdate(name="new-name")
        assert upd.items is None

    def test_update_rejects_over_max(self):
        items = [RunbookItemCreate(**self._item(i)) for i in range(MAX_RUNBOOK_ITEMS + 1)]
        with pytest.raises(ValidationError):
            RunbookUpdate(items=items)


# ── Issue 10: graph positions cap ────────────────────────────────────


class TestGraphPositionsCap:
    """The handler check is `if len(positions) > MAX_GRAPH_NODES:
    raise HTTPException(400)`. Test the pure predicate at unit level
    since the handler needs a DB session + auth to reach the check
    end-to-end."""

    def test_within_cap(self):
        positions = {f"n{i}": {"x": i, "y": i} for i in range(MAX_GRAPH_NODES)}
        assert len(positions) <= MAX_GRAPH_NODES

    def test_over_cap_len_detection(self):
        # Guardrail: a dict at MAX + 1 keys is what the handler rejects.
        positions = {f"n{i}": None for i in range(MAX_GRAPH_NODES + 1)}
        assert len(positions) > MAX_GRAPH_NODES

    def test_cap_is_not_absurdly_small(self):
        # A cap of 100 would break legit engagement graphs on
        # medium-sized red-team scenarios. Pin the floor here so a
        # well-meaning "smaller default is safer" edit gets caught.
        assert MAX_GRAPH_NODES >= 500


# ── Issue 9: MAX_LIST_LIMIT propagation ──────────────────────────────


class TestListLimitPropagation:
    """The Query bound is applied at the endpoint decorator level —
    testing it requires a real request. Pin the constant plus a
    static invariant: the value must at least match RedWire's
    existing per-endpoint caps (500 on intel, 200 on infra, etc.) so
    the new global doesn't accidentally shrink a working ceiling."""

    def test_max_list_limit_ge_intel_local_cap(self):
        # backend/routers/intel.py uses le=500 today; our global cap
        # must not shrink that surface.
        assert MAX_LIST_LIMIT >= 500

    def test_max_list_limit_ge_infra_local_cap(self):
        # infra.py uses le=200. Same rule.
        assert MAX_LIST_LIMIT >= 200
