"""Unit coverage for three realtime / automation helpers that had none:
_match_condition's operator table, the activity feed's update-diff
correlation, and the presence registry's pruning of dead workers."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest


# ── _match_condition ─────────────────────────────────────────────────────

def _m(field, operator, value, **ctx):
    from utils.automation_engine import _match_condition
    return _match_condition({"field": field, "operator": operator, "value": value}, ctx)


@pytest.mark.parametrize("operator,value,actual,expected", [
    ("equals", "High", "HIGH", True),            # case-insensitive
    ("equals", "high", "MEDIUM", False),
    ("not_equals", "high", "MEDIUM", True),
    ("not_equals", "HIGH", "high", False),
    ("contains", "SQL", "Blind sql injection", True),
    ("contains", "xss", "Blind sql injection", False),
    ("in", "low, medium ,HIGH", "high", True),   # comma list, trimmed
    ("in", "low,medium", "high", False),
    ("has_any", "a,b", "b", True),
    ("has_none", "a,b", "c", True),
    ("has_none", "a,b", "a", False),
    ("bogus", "x", "x", False),                  # unknown operator never matches
])
def test_scalar_operators(operator, value, actual, expected):
    assert _m("severity", operator, value, severity=actual) is expected


@pytest.mark.parametrize("operator,value,actual,expected", [
    ("gt", "7", 7.5, True), ("gt", "7.5", 7.5, False),
    ("gte", "7.5", 7.5, True), ("lt", 4, "3.9", True),
    ("lte", "3", 3, True), ("lte", "3", 3.01, False),
    ("gt", "seven", 9, False),                   # non-numeric expected
    ("gt", "1", "n/a", False),                   # non-numeric actual
])
def test_numeric_operators(operator, value, actual, expected):
    assert _m("cvss_score", operator, value, cvss_score=actual) is expected


@pytest.mark.parametrize("operator,value,expected", [
    ("has_any", "SQLi, rce", True),
    ("in", ["xss", "rce"], False),
    ("has_all", "critical,sqli", True),
    ("has_all", "critical,rce", False),
    ("has_all", "", True),                       # nothing required
    ("has_none", "rce,xss", True),
    ("not_equals", "sqli", False),               # on a list = "not present"
    ("equals", "Critical", True),                # on a list = "present"
    ("equals", "rce", False),
    ("contains", "sql", True),                   # substring of an element
    ("bogus", "sqli", False),
])
def test_list_operators(operator, value, expected):
    assert _m("tags", operator, value, tags=["critical", "SQLi"]) is expected


def test_missing_field_never_matches_even_negated():
    assert _m("severity", "not_equals", "high") is False
    assert _m("tags", "has_none", "x", tags=None) is False


def test_default_operator_is_equals():
    from utils.automation_engine import _match_condition
    assert _match_condition({"field": "status", "value": "open"}, {"status": "OPEN"})


def test_all_conditions_are_anded():
    from utils.automation_engine import _all_conditions_match
    ctx = {"severity": "HIGH", "cvss_score": 8.1}
    hi = {"field": "severity", "operator": "equals", "value": "high"}
    assert _all_conditions_match([], ctx)
    assert _all_conditions_match([hi, {"field": "cvss_score", "operator": "gte", "value": "8"}], ctx)
    assert not _all_conditions_match([hi, {"field": "cvss_score", "operator": "gte", "value": "9"}], ctx)


# ── _feed_diff_for_update ────────────────────────────────────────────────

T0 = datetime(2026, 11, 28, 12, 0, 0)
FIELDS = ["title", "severity", "description"]


def _snap(version, at, snapshot, changed=None):
    return SimpleNamespace(version=version, created_at=at, snapshot=snapshot, changed_fields=changed)


def _diff(log_at, snapshots, entity=None):
    from routers.discussions import _feed_diff_for_update
    return _feed_diff_for_update({"created_at": log_at.isoformat()}, snapshots, entity, FIELDS)


def test_latest_edit_diffs_snapshot_against_live_entity():
    sev = SimpleNamespace(value="HIGH")  # enums are scalarized
    entity = SimpleNamespace(title="New", severity=sev, description="same")
    snaps = [_snap(1, T0 - timedelta(milliseconds=3), {"title": "Old", "severity": "LOW", "description": "same"})]
    out = _diff(T0, snaps, entity)
    assert [(c["field"], c["label"], c["old"], c["new"]) for c in out] == [
        ("title", "Title", "Old", "New"), ("severity", "Severity", "LOW", "HIGH")]


def test_older_edit_diffs_against_the_next_snapshot():
    snaps = [
        _snap(1, T0, {"title": "A", "severity": "LOW", "description": "d"}),
        _snap(2, T0 + timedelta(minutes=5), {"title": "B", "severity": "LOW", "description": "d"}),
    ]
    entity = SimpleNamespace(title="C", severity="LOW", description="d")
    assert [(c["old"], c["new"]) for c in _diff(T0 + timedelta(milliseconds=2), snaps, entity)] == [("A", "B")]
    # The second edit pairs with snapshot 2 and the live entity.
    assert [(c["old"], c["new"]) for c in _diff(T0 + timedelta(minutes=5, milliseconds=1), snaps, entity)] == [("B", "C")]


def test_changed_fields_limits_the_diff():
    snaps = [_snap(1, T0, {"title": "A", "severity": "LOW", "description": "x"}, changed=["severity"])]
    entity = SimpleNamespace(title="B", severity="HIGH", description="y")
    assert [c["field"] for c in _diff(T0, snaps, entity)] == ["severity"]


def test_no_plausible_snapshot_gives_no_diff():
    snaps = [_snap(1, T0, {"title": "A"})]
    entity = SimpleNamespace(title="B", severity=None, description=None)
    assert _diff(T0 + timedelta(seconds=30), snaps, entity) == [], "snapshot too far before the log"
    assert _diff(T0 - timedelta(seconds=5), snaps, entity) == [], "snapshot after the log"
    assert _diff(T0, [], entity) == []
    from routers.discussions import _feed_diff_for_update
    assert _feed_diff_for_update({"created_at": None}, snaps, entity, FIELDS) == []


def test_long_values_are_capped():
    from routers.discussions import _FEED_CONTENT_CAP
    snaps = [_snap(1, T0, {"title": "", "severity": None, "description": "a"})]
    entity = SimpleNamespace(title="", severity=None, description="b" * (_FEED_CONTENT_CAP + 50))
    (c,) = _diff(T0, snaps, entity)
    assert c["new"].endswith("… (truncated)") and len(c["new"]) < _FEED_CONTENT_CAP + 20


# ── presence pruning ─────────────────────────────────────────────────────

@pytest.fixture
async def bus():
    from utils import ws_bus
    b = ws_bus.WsBus()
    os.environ.setdefault("WS_FANOUT", "true")
    await b.start()
    if not b.active:
        pytest.skip("Redis not reachable")
    yield b
    await b.stop()


async def test_presence_list_prunes_dead_workers_only(bus):
    from utils import ws_bus
    rt, rid = "finding", uuid.uuid4().hex
    key = bus._presence_key(rt, rid)
    live_w, dead_w = "live" + uuid.uuid4().hex[:8], "dead" + uuid.uuid4().hex[:8]
    try:
        await bus.presence_add(rt, rid, "c1", {"user_id": "me"})
        await bus._redis.set(ws_bus._WORKER_PREFIX + live_w, "1", ex=60)
        await bus._redis.hset(key, mapping={
            f"{live_w}:c2": json.dumps({"user_id": "peer"}),
            f"{dead_w}:c3": json.dumps({"user_id": "ghost"}),
            f"{live_w}:c4": "not json",
        })
        users = sorted(u["user_id"] for u in await bus.presence_list(rt, rid))
        assert users == ["me", "peer"]
        left = await bus._redis.hkeys(key)
        assert f"{dead_w}:c3" not in left, "a dead worker's entries are removed, not just hidden"
        assert f"{live_w}:c2" in left and f"{ws_bus.WORKER_ID}:c1" in left
    finally:
        await bus._redis.delete(key, ws_bus._WORKER_PREFIX + live_w)


async def test_presence_list_is_none_without_redis():
    from utils import ws_bus
    b = ws_bus.WsBus()  # never started
    assert await b.presence_list("finding", "x") is None
