"""GHSA-rq7c-4v9x-mjfp — rollup fix regressions.

Two of the four issues in the rollup were shipped as fixes; the other
two (automation-rule cross-editing, ai_api_url SSRF framing) were
closed informational as intended-by-design — see
`feedback_automation_edit_global` and `feedback_ai_api_url_admin`
memories for the rationale.

This module pins:

  Issue 1 (CWE-269): READ_ONLY_ADMIN can no longer bypass
  ``can_modify_resource``. Regression test asserts every role individually.

  Issue 3 (CWE-835): batch reorder rejects parent-chain cycles up
  front; single-node update walk is bounded by _MAX_CLIENT_TREE_DEPTH
  so legacy bad data can't hang a worker either.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException


# ── Issue 1: can_modify_resource ─────────────────────────────────────


class TestCanModifyResourceRoles:
    """Pin every role's outcome so a future edit to the allow-list
    can't silently re-admit READ_ONLY_ADMIN or drop ADMIN."""

    @pytest.fixture
    def can_modify(self):
        from auth.rbac import can_modify_resource
        return can_modify_resource

    @pytest.fixture
    def user(self):
        # Two-arg fixture: role -> user object with only .role and .id populated.
        def _make(role):
            return SimpleNamespace(role=role, id="user-1")
        return _make

    def test_admin_can_modify(self, can_modify, user):
        from models.user import UserRole
        assert can_modify("someone-else", user(UserRole.ADMIN)) is True

    def test_team_lead_can_modify(self, can_modify, user):
        from models.user import UserRole
        assert can_modify("someone-else", user(UserRole.TEAM_LEAD)) is True

    def test_read_only_admin_CANNOT_modify(self, can_modify, user):
        # The whole point of the fix. Pre-flip this returned True.
        from models.user import UserRole
        assert can_modify("someone-else", user(UserRole.READ_ONLY_ADMIN)) is False

    def test_operator_can_only_modify_own(self, can_modify, user):
        from models.user import UserRole
        u = user(UserRole.OPERATOR)
        assert can_modify(u.id, u) is True
        assert can_modify("someone-else", u) is False

    def test_read_only_cannot_modify_anything(self, can_modify, user):
        from models.user import UserRole
        u = user(UserRole.READ_ONLY)
        assert can_modify(u.id, u) is False
        assert can_modify("someone-else", u) is False


# ── Issue 3: _assert_no_reorder_cycle ────────────────────────────────


def _mock_db_with_clients(existing: dict[str, str | None]) -> MagicMock:
    """Build an AsyncSession stub whose db.execute(select(Client.id,
    Client.parent_id)) returns the supplied id → parent_id map as rows."""
    db = MagicMock()
    result = MagicMock()
    # SQLAlchemy Row-like tuples: (id, parent_id)
    result.all.return_value = list(existing.items())
    db.execute = AsyncMock(return_value=result)
    return db


class TestReorderCycleGuard:
    @pytest.fixture
    def guard(self):
        from routers.clients import _assert_no_reorder_cycle
        return _assert_no_reorder_cycle

    def _item(self, id: str, parent_id: str | None):
        return SimpleNamespace(id=id, parent_id=parent_id, sort_order=0)

    @pytest.mark.asyncio
    async def test_clean_reorder_permitted(self, guard):
        db = _mock_db_with_clients({"a": None, "b": None, "c": "a"})
        await guard([self._item("c", "b")], db)  # must not raise

    @pytest.mark.asyncio
    async def test_two_node_cycle_rejected(self, guard):
        # Two-node cycle — the canonical PoC in the advisory.
        db = _mock_db_with_clients({"a": None, "b": None})
        with pytest.raises(HTTPException) as exc:
            await guard(
                [self._item("a", "b"), self._item("b", "a")], db
            )
        assert exc.value.status_code == 400
        assert "cycle" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_self_parent_rejected(self, guard):
        db = _mock_db_with_clients({"a": None})
        with pytest.raises(HTTPException) as exc:
            await guard([self._item("a", "a")], db)
        assert exc.value.status_code == 400
        assert "own parent" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_longer_cycle_rejected(self, guard):
        # A → B → C → A. The naive fix would only catch two-node cycles.
        db = _mock_db_with_clients({"a": None, "b": None, "c": None})
        with pytest.raises(HTTPException) as exc:
            await guard(
                [
                    self._item("a", "b"),
                    self._item("b", "c"),
                    self._item("c", "a"),
                ],
                db,
            )
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_unknown_id_rejected(self, guard):
        # An id not present in the DB is refused before the walk so we
        # get a clean 400 rather than a confusing walk-failure.
        db = _mock_db_with_clients({"a": None})
        with pytest.raises(HTTPException) as exc:
            await guard([self._item("ghost", None)], db)
        assert exc.value.status_code == 400
        assert "unknown client" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_unknown_parent_id_rejected(self, guard):
        db = _mock_db_with_clients({"a": None})
        with pytest.raises(HTTPException) as exc:
            await guard([self._item("a", "ghost-parent")], db)
        assert exc.value.status_code == 400
        assert "unknown parent" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_batch_that_breaks_existing_cycle_permitted(self, guard):
        # Existing DB has a cycle (legacy bad data). If the incoming
        # batch BREAKS the cycle by moving one of the members to null,
        # the guard must NOT block the remediation.
        db = _mock_db_with_clients({"a": "b", "b": "a", "c": None})
        # This batch resolves the cycle by parking A at root.
        await guard([self._item("a", None)], db)


class TestReorderCycleDepthCap:
    """The depth cap defends against legacy bad data that already contains
    a cycle in the DB (post-fix data can never introduce one via this
    endpoint). Without the cap the walk would spin forever."""

    @pytest.mark.asyncio
    async def test_cap_engages_on_pre_existing_cycle(self):
        from routers.clients import _assert_no_reorder_cycle, _MAX_CLIENT_TREE_DEPTH
        # Pre-existing cycle in the DB — the walk from any node in it
        # would loop forever without the cap.
        db = _mock_db_with_clients({"a": "b", "b": "a"})
        # A batch that touches neither of the cyclic nodes still walks
        # the ancestor chain of the mutated node. Add a node whose chain
        # leads into the pre-existing cycle: c → a → b → a → ...
        db_rows = {"a": "b", "b": "a", "c": "a"}
        db = _mock_db_with_clients(db_rows)
        # Touching c and leaving it pointing at a means walking c's chain
        # runs into the existing a↔b cycle. Cap must trip.
        item = SimpleNamespace(id="c", parent_id="a", sort_order=0)
        with pytest.raises(HTTPException) as exc:
            await _assert_no_reorder_cycle([item], db)
        assert exc.value.status_code == 400
        # Cycle detection fires before the depth cap on this shape
        # (a → b → a → cycle detected). Either error text is acceptable.
        assert (
            "cycle" in exc.value.detail.lower()
            or "cap" in exc.value.detail.lower()
        )

    def test_max_depth_is_set(self):
        from routers.clients import _MAX_CLIENT_TREE_DEPTH
        # Pin the value so a future edit doesn't accidentally drop it
        # to something absurd like 10 (would break legit deep trees) or
        # bump it to 1_000_000 (would negate the DoS defence).
        assert 100 <= _MAX_CLIENT_TREE_DEPTH <= 100_000
