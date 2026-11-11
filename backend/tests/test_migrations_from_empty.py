"""The migration chain builds a working schema from an empty database, and
the result matches the models.

The rest of the suite builds its schema with ``Base.metadata.create_all``,
so it never exercises the migrations: a revision that only works on top of
existing data, a broken down_revision, or a model change nobody generated a
migration for would all pass it. This runs the real ``migrate.py upgrade
heads`` (core + plugin migration dirs) against a fresh throwaway database,
then ``migrate.py check`` (alembic's model-vs-schema comparison), then
upgrades again to prove re-running is a no-op.

It takes ~10-60 s. Skip with SKIP_MIGRATION_TEST=1.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

import asyncpg
import pytest

from tests.conftest import _test_db_url

BACKEND = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.skipif(os.getenv("SKIP_MIGRATION_TEST") == "1", reason="SKIP_MIGRATION_TEST=1")


def _dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _migrate(db_url: str, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "DATABASE_URL": db_url}
    return subprocess.run(
        [sys.executable, "migrate.py", *args], cwd=BACKEND, env=env,
        capture_output=True, text=True, timeout=600,
    )


async def test_migrations_build_the_model_schema_from_empty():
    base, _, _ = _test_db_url().rpartition("/")
    name = f"redwire_migtest_{uuid.uuid4().hex[:8]}"
    admin = await asyncpg.connect(_dsn(f"{base}/postgres"))
    try:
        await admin.execute(f'CREATE DATABASE "{name}"')
        url = f"{base}/{name}"

        up = _migrate(url, "upgrade", "heads")
        assert up.returncode == 0, f"upgrade heads failed:\n{up.stdout[-4000:]}\n{up.stderr[-4000:]}"

        check = _migrate(url, "check")
        assert check.returncode == 0, (
            "schema built by migrations differs from the models — generate a migration:\n"
            f"{check.stdout[-4000:]}\n{check.stderr[-4000:]}"
        )

        again = _migrate(url, "upgrade", "heads")
        assert again.returncode == 0, f"re-running upgrade failed:\n{again.stderr[-4000:]}"

        conn = await asyncpg.connect(_dsn(url))
        try:
            heads = await conn.fetch("SELECT version_num FROM alembic_version")
        finally:
            await conn.close()
        assert heads, "alembic_version is empty after upgrade"
    finally:
        await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        await admin.close()
