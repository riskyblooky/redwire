"""GHSA-7x2f-ff7r-h388 deferred #12 — version-history race guarded.

Two layers of defence:

  1. **DB-level**: `UniqueConstraint('entity_type', 'entity_id',
     'version')` restored by Alembic revision 199be698dd4a. A losing
     concurrent writer's INSERT is refused at commit time.
  2. **App-level**: `create_version_snapshot` wraps its INSERT in a
     `db.begin_nested()` SAVEPOINT + retry loop. On IntegrityError
     the SAVEPOINT rolls back (outer transaction unaffected) and we
     re-read MAX and try again — up to
     `_VERSION_INSERT_MAX_RETRIES` (5) times.

These tests pin the app-level pieces via static-shape assertions
(the retry constant + the loop shape + the SAVEPOINT wrapper +
IntegrityError catch) so a future refactor that reverts to the
single-shot INSERT reappears loudly here. The DB-level piece is
exercised by the live smoke documented in the commit message.
"""

from __future__ import annotations

import os

import pytest
from cryptography.fernet import Fernet

os.environ.setdefault("TOTP_ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ.setdefault("VAULT_ENCRYPTION_KEY", Fernet.generate_key().decode())


# ── Model-level: unique constraint on the ORM class ─────────────────


class TestModelUniqueConstraint:
    def test_table_args_declares_unique(self):
        from models.version_history import VersionHistory
        # __table_args__ is a tuple of Constraint objects. Find the
        # UniqueConstraint on (entity_type, entity_id, version).
        args = VersionHistory.__table_args__
        from sqlalchemy import UniqueConstraint
        uqs = [c for c in args if isinstance(c, UniqueConstraint)]
        assert len(uqs) == 1
        cols = [col.name for col in uqs[0].columns]
        assert cols == ["entity_type", "entity_id", "version"]


# ── Helper-level: retry loop shape ───────────────────────────────────


class TestRetryLoopShape:
    def _versioning_src(self) -> str:
        return open("/app/utils/versioning.py").read()

    def test_max_retries_constant_present(self):
        src = self._versioning_src()
        assert "_VERSION_INSERT_MAX_RETRIES = 5" in src

    def test_savepoint_wrapper_present(self):
        # The nested-begin is what protects the outer transaction from
        # the rolled-back INSERT on a collision.
        src = self._versioning_src()
        assert "db.begin_nested()" in src

    def test_integrity_error_caught(self):
        src = self._versioning_src()
        assert "from sqlalchemy.exc import IntegrityError" in src
        assert "except IntegrityError" in src

    def test_loop_wraps_read_and_insert(self):
        # Regression pin — the MAX read must be INSIDE the loop so
        # a retry re-reads the current MAX. A single-read + retry-
        # insert would keep trying the same doomed version number.
        src = self._versioning_src()
        loop_idx = src.find("for attempt in range(_VERSION_INSERT_MAX_RETRIES)")
        max_read_idx = src.find("select(func.coalesce(func.max(VersionHistory.version)", loop_idx)
        assert loop_idx != -1 and max_read_idx != -1
        assert loop_idx < max_read_idx, "MAX read must be inside the retry loop"

    def test_no_regression_to_single_shot_insert(self):
        # Before the fix, the flow was:
        #   result = await db.execute(select(max))
        #   next_version = result.scalar() + 1
        #   db.add(VersionHistory(... version=next_version ...))
        # WITHOUT any loop or savepoint. Pin that the retry loop
        # remains — and that a bare `next_version = result.scalar() + 1`
        # doesn't appear OUTSIDE the loop.
        src = self._versioning_src()
        loop_idx = src.find("for attempt in range(_VERSION_INSERT_MAX_RETRIES)")
        assert loop_idx != -1
        # The `.scalar() + 1` construct should only appear inside the
        # loop (which starts at loop_idx). No stray copy outside.
        preloop = src[:loop_idx]
        assert "result.scalar() + 1" not in preloop, (
            "single-shot MAX-read + next_version compute must not appear before the retry loop"
        )


# ── Alembic migration presence ──────────────────────────────────────


class TestMigrationPresent:
    def test_dedupe_and_index_migration_exists(self):
        import glob
        matches = glob.glob(
            "/app/alembic/versions/*199be698dd4a*.py"
        )
        assert matches, "expected migration 199be698dd4a to be present"
        src = open(matches[0]).read()
        # Must dedupe BEFORE creating the constraint — otherwise the
        # DDL fails on any DB where the race already produced dupes.
        dedupe_idx = src.find("DELETE FROM version_history")
        create_idx = src.find("create_unique_constraint")
        assert dedupe_idx != -1 and create_idx != -1
        assert dedupe_idx < create_idx, (
            "dedupe must precede unique-constraint creation"
        )

    def test_dedupe_keeps_oldest(self):
        # Regression pin: ORDER BY created_at ASC ensures we keep the
        # earliest row per key, which is the deterministic choice for
        # audit trail (older event's snapshot is the "authoritative"
        # one for that version number).
        import glob
        src = open(glob.glob("/app/alembic/versions/*199be698dd4a*.py")[0]).read()
        assert "ORDER BY created_at ASC" in src
