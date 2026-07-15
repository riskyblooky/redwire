"""Version-history snapshot logic (`utils/versioning.py`).

The existing `test_7x2f_deferred_12.py` pins the *source shape* of the
retry loop; this file covers the runtime *behaviour* of the pure helpers
and `create_version_snapshot`:

  - `_snapshot_entity`: field selection, enum→value, missing→None
  - `_detect_changed_fields`: change detection, enum normalisation on the
    new value, and ignoring keys not in the snapshot
  - `create_version_snapshot`: skip-when-nothing-changed, the happy-path
    INSERT (version = MAX+1, snapshot + changed_fields carried), the
    retry-on-IntegrityError loop, and the give-up-after-N-retries path
    (drops the snapshot, never raises to the caller).

`create_version_snapshot` needs an AsyncSession that offers `execute`,
`add`, and an async `begin_nested()` context manager, so a small local
fake stands in (the shared FakeDb has no `begin_nested`).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy.exc import IntegrityError

from tests.conftest import FakeScalarResult
from utils.versioning import (
    FINDING_VERSIONED_FIELDS,
    TESTCASE_VERSIONED_FIELDS,
    _VERSION_INSERT_MAX_RETRIES,
    _detect_changed_fields,
    _snapshot_entity,
    create_version_snapshot,
)


class _Enum:
    """Minimal enum-like with a `.value` (mirrors SQLAlchemy enum columns)."""

    def __init__(self, value):
        self.value = value


# ── _snapshot_entity ─────────────────────────────────────────────────


class TestSnapshotEntity:
    def test_selects_only_named_fields(self):
        entity = SimpleNamespace(title="A", description="D", secret="nope")
        snap = _snapshot_entity(entity, ["title", "description"])
        assert snap == {"title": "A", "description": "D"}

    def test_missing_field_becomes_none(self):
        entity = SimpleNamespace(title="A")
        snap = _snapshot_entity(entity, ["title", "cvss_score"])
        assert snap == {"title": "A", "cvss_score": None}

    def test_enum_values_unwrapped(self):
        entity = SimpleNamespace(severity=_Enum("CRITICAL"), status=_Enum("OPEN"))
        snap = _snapshot_entity(entity, ["severity", "status"])
        assert snap == {"severity": "CRITICAL", "status": "OPEN"}

    def test_plain_values_preserved(self):
        entity = SimpleNamespace(cvss_score=7.5, references=["a", "b"])
        snap = _snapshot_entity(entity, ["cvss_score", "references"])
        assert snap == {"cvss_score": 7.5, "references": ["a", "b"]}


# ── _detect_changed_fields ───────────────────────────────────────────


class TestDetectChangedFields:
    def test_detects_a_changed_value(self):
        snap = {"title": "old", "severity": "LOW"}
        assert _detect_changed_fields(snap, {"title": "new"}) == ["title"]

    def test_no_change_when_equal(self):
        snap = {"title": "same"}
        assert _detect_changed_fields(snap, {"title": "same"}) == []

    def test_ignores_keys_not_in_snapshot(self):
        # update_data may carry non-versioned fields — they must not count.
        snap = {"title": "x"}
        assert _detect_changed_fields(snap, {"assignee_id": "u1"}) == []

    def test_enum_new_value_normalised_before_compare(self):
        # Snapshot holds the string form; a new enum-valued update that
        # matches must NOT be flagged as a change.
        snap = {"severity": "HIGH"}
        assert _detect_changed_fields(snap, {"severity": _Enum("HIGH")}) == []

    def test_enum_new_value_change_detected(self):
        snap = {"severity": "HIGH"}
        assert _detect_changed_fields(snap, {"severity": _Enum("CRITICAL")}) == ["severity"]

    def test_multiple_changes_preserve_update_order(self):
        snap = {"title": "a", "status": "OPEN", "impact": "i"}
        changed = _detect_changed_fields(
            snap, {"title": "b", "status": "OPEN", "impact": "j"})
        assert changed == ["title", "impact"]

    def test_none_to_value_is_a_change(self):
        snap = {"notes": None}
        assert _detect_changed_fields(snap, {"notes": "added"}) == ["notes"]


# ── field-list wiring sanity ─────────────────────────────────────────


class TestVersionedFieldLists:
    def test_finding_fields_include_core_columns(self):
        for f in ("title", "severity", "cvss_score", "status"):
            assert f in FINDING_VERSIONED_FIELDS

    def test_testcase_fields_include_core_columns(self):
        for f in ("title", "steps", "expected_result", "is_executed"):
            assert f in TESTCASE_VERSIONED_FIELDS


# ── create_version_snapshot: a fake AsyncSession ─────────────────────


class _FakeNested:
    """Async context manager returned by `begin_nested()`.

    On `__aexit__` it raises IntegrityError for the first `fail_times`
    invocations to simulate a losing concurrent writer, mirroring how the
    real SAVEPOINT commit rejects a unique-constraint collision.
    """

    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        self._db.nested_entries += 1
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._db.remaining_failures > 0:
            self._db.remaining_failures -= 1
            raise IntegrityError("INSERT", {}, Exception("duplicate key"))
        return False


class _FakeVersionDb:
    def __init__(self, current_max=0, fail_times=0):
        self._current_max = current_max
        self.remaining_failures = fail_times
        self.added: list = []
        self.execute_count = 0
        self.nested_entries = 0

    async def execute(self, _query, *a, **k):
        # Every MAX read returns the same current max; next_version = max + 1.
        self.execute_count += 1
        return FakeScalarResult(self._current_max)

    def add(self, obj):
        self.added.append(obj)

    def begin_nested(self):
        return _FakeNested(self)


def _finding(id="f-1", **fields):
    base = dict(
        title="t", category="c", description="d", severity=_Enum("HIGH"),
        status=_Enum("OPEN"), cvss_score=7.0, cvss_vector="AV:N",
        impact="i", technical_details="td", steps_to_reproduce="s",
        mitigations="m", references="r",
    )
    base.update(fields)
    return SimpleNamespace(id=id, **base)


class TestCreateVersionSnapshot:
    async def test_no_change_skips_insert(self):
        db = _FakeVersionDb()
        entity = _finding(title="same")
        # update_data equals current state → nothing changed → no MAX read,
        # no INSERT.
        await create_version_snapshot(
            db, entity, "finding", {"title": "same"}, "user-1")
        assert db.added == []
        assert db.execute_count == 0
        assert db.nested_entries == 0

    async def test_happy_path_inserts_version_max_plus_one(self):
        db = _FakeVersionDb(current_max=4)
        entity = _finding(title="old")
        await create_version_snapshot(
            db, entity, "finding", {"title": "new"}, "user-1")
        assert len(db.added) == 1
        row = db.added[0]
        assert row.entity_type == "finding"
        assert row.entity_id == "f-1"
        assert row.version == 5                 # MAX(4) + 1
        assert row.changed_by == "user-1"
        assert row.changed_fields == ["title"]
        # Snapshot captured the PRE-update state (enum unwrapped to string).
        assert row.snapshot["title"] == "old"
        assert row.snapshot["severity"] == "HIGH"
        assert db.nested_entries == 1

    async def test_first_insert_version_is_one_on_empty_history(self):
        db = _FakeVersionDb(current_max=0)
        await create_version_snapshot(
            db, _finding(title="old"), "finding", {"title": "new"}, None)
        assert db.added[0].version == 1
        assert db.added[0].changed_by is None

    async def test_testcase_entity_type_uses_testcase_fields(self):
        db = _FakeVersionDb(current_max=0)
        entity = SimpleNamespace(
            id="tc-1", title="old", category="c", description="d",
            steps="s", expected_result="e", actual_result="a",
            is_executed=False, is_successful=None, notes="n")
        await create_version_snapshot(
            db, entity, "testcase", {"is_executed": True}, "u")
        row = db.added[0]
        assert row.entity_type == "testcase"
        assert row.changed_fields == ["is_executed"]
        assert "steps" in row.snapshot and "title" in row.snapshot

    async def test_retries_on_collision_then_succeeds(self):
        # First two SAVEPOINT commits collide, third succeeds.
        db = _FakeVersionDb(current_max=2, fail_times=2)
        await create_version_snapshot(
            db, _finding(title="old"), "finding", {"title": "new"}, "u")
        # Three attempts total: two failed + one committed.
        assert db.nested_entries == 3
        assert db.execute_count == 3            # MAX re-read each attempt
        assert db.remaining_failures == 0

    async def test_gives_up_after_max_retries_without_raising(self):
        # Every attempt collides → the helper must swallow it and return,
        # NOT propagate to the caller (audit entry lost, update survives).
        db = _FakeVersionDb(current_max=0, fail_times=_VERSION_INSERT_MAX_RETRIES)
        result = await create_version_snapshot(
            db, _finding(title="old"), "finding", {"title": "new"}, "u")
        assert result is None
        assert db.nested_entries == _VERSION_INSERT_MAX_RETRIES
        assert db.execute_count == _VERSION_INSERT_MAX_RETRIES
