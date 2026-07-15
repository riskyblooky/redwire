"""Shared pytest fixtures and fakes for the RedWire backend suite.

Two layers live here:

1. **Pure-unit fakes** (``FakeDb``, ``FakeScalarResult``, ``make_fake_user``)
   — lightweight stand-ins so a test can exercise a helper that expects an
   ``AsyncSession`` / a ``User`` without touching a database. This mirrors
   the fakes that several existing tests hand-rolled inline; they're
   centralised here so new tests don't copy-paste them.

2. **DB-integration harness** (``db_engine``, ``db_session``, ``client``,
   ``make_user``, ``authenticate_as``) — a real async Postgres session and an
   httpx ``AsyncClient`` bound to the FastAPI app, so router endpoints can be
   driven end-to-end. Each test runs inside a transaction that is rolled back
   on teardown, so tests never see each other's writes and the DB is never
   left dirty.

The integration layer needs a Postgres database (the app models use
Postgres-specific types and an at-rest-encrypted column). It points at
``TEST_DATABASE_URL`` if set, otherwise derives ``<db>_test`` from the app's
``DATABASE_URL``. Create it once with::

    docker compose exec postgres psql -U redwire -d postgres -c "CREATE DATABASE redwire_test;"

Run the suite inside the backend container so the env (VAULT_ENCRYPTION_KEY,
JWT_SECRET, DB network) is present::

    docker compose exec backend python -m pytest
"""

from __future__ import annotations

import os
import uuid
from typing import Any, Callable, Optional

import pytest
import pytest_asyncio
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool


# ─────────────────────────────────────────────────────────────────────────
# 1. Pure-unit fakes (no DB)
# ─────────────────────────────────────────────────────────────────────────


class FakeScalarResult:
    """Stand-in for the object returned by ``await session.execute(...)``.

    Covers the handful of accessors router/helper code actually calls on a
    result: ``scalar_one_or_none``, ``scalar``, ``scalars().all()``,
    ``scalars().first()``. Queue whichever value the code-under-test expects
    to pull.
    """

    def __init__(self, value: Any = None, *, many: Optional[list] = None):
        self._value = value
        self._many = many if many is not None else ([] if value is None else [value])

    def scalar_one_or_none(self):
        return self._value

    def scalar(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        return list(self._many)

    def first(self):
        return self._many[0] if self._many else None


class FakeDb:
    """Minimal async ``AsyncSession`` fake.

    ``execute`` pops the next queued result (or returns an empty
    ``FakeScalarResult`` when the queue is drained). ``add`` / ``commit`` /
    ``rollback`` / ``refresh`` / ``flush`` / ``delete`` are recorded so a test
    can assert on them without a real transaction.
    """

    def __init__(self, results: Optional[list] = None):
        self._results = list(results or [])
        self.added: list = []
        self.deleted: list = []
        self.commit_count = 0
        self.rollback_count = 0
        self.flush_count = 0

    async def execute(self, _query, *args, **kwargs):
        if self._results:
            nxt = self._results.pop(0)
            return nxt if isinstance(nxt, FakeScalarResult) else FakeScalarResult(nxt)
        return FakeScalarResult(None)

    def add(self, obj):
        self.added.append(obj)

    async def delete(self, obj):
        self.deleted.append(obj)

    async def commit(self):
        self.commit_count += 1

    async def rollback(self):
        self.rollback_count += 1

    async def flush(self):
        self.flush_count += 1

    async def refresh(self, obj, *args, **kwargs):
        return obj

    async def close(self):
        pass


def make_fake_user(role: str = "operator", **overrides) -> Any:
    """Build a ``User``-shaped object for pure-unit tests that only read
    attributes (``id``, ``role``, ``is_active``, ...). Uses the real
    ``UserRole`` enum so ``.role.value`` comparisons behave like production.
    """
    from types import SimpleNamespace

    from models.user import UserRole

    role_enum = role if isinstance(role, UserRole) else UserRole(role)
    attrs = dict(
        id=str(uuid.uuid4()),
        username=f"user_{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@test.local",
        role=role_enum,
        is_active=True,
        groups=[],
    )
    attrs.update(overrides)
    return SimpleNamespace(**attrs)


# ─────────────────────────────────────────────────────────────────────────
# 2. DB-integration harness (real Postgres + httpx client)
# ─────────────────────────────────────────────────────────────────────────


def _test_db_url() -> str:
    explicit = os.getenv("TEST_DATABASE_URL")
    if explicit:
        return explicit
    app_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://redwire:changeme@postgres:5432/redwire",
    )
    # Swap the trailing database name for "<name>_test" without disturbing
    # host/credentials. rsplit keeps any '/' that appears earlier in creds.
    base, _, name = app_url.rpartition("/")
    return f"{base}/{name}_test"


@pytest_asyncio.fixture(scope="session")
async def db_engine():
    """Session-scoped engine against the test database.

    Drops and recreates the ``public`` schema once per session, then builds
    every table from the models' metadata. Recreating the schema (rather than
    just ``drop_all``) guarantees a clean slate even if a previous crashed run
    left Postgres enum types behind.
    """
    # Importing main registers every model on Base.metadata and gives us the
    # configured FastAPI app. No DB work happens at import time.
    import main  # noqa: F401
    from database import Base

    engine = create_async_engine(_test_db_url(), poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    """Function-scoped session wrapped in a transaction that is rolled back.

    Uses the SQLAlchemy "join an external transaction" recipe so that even
    when the code-under-test calls ``session.commit()`` (many routers do), the
    commit only releases a SAVEPOINT — the outer transaction is still rolled
    back on teardown, leaving the database pristine for the next test.
    """
    async with db_engine.connect() as conn:
        await conn.begin()
        await conn.begin_nested()
        Session = async_sessionmaker(bind=conn, expire_on_commit=False, autoflush=False)
        session = Session()

        @event.listens_for(session.sync_session, "after_transaction_end")
        def _restart_savepoint(sess, trans):
            # When the app's commit ends the SAVEPOINT, immediately open a
            # fresh one so subsequent statements stay inside the outer
            # (rolled-back) transaction.
            if conn.closed:
                return
            if not conn.in_nested_transaction():
                conn.sync_connection.begin_nested()

        try:
            yield session
        finally:
            await session.close()
        # Exiting the `async with` rolls the outer transaction back.


@pytest_asyncio.fixture
async def client(db_session):
    """httpx AsyncClient bound to the FastAPI app with ``get_db`` overridden
    to the test session.

    No auth override is applied here — use this to test unauthenticated paths
    (401s, the login endpoint). For authenticated calls, use
    ``authenticate_as`` to install a current-user override.

    The client is built with ASGITransport WITHOUT running the app lifespan,
    so the heavy startup work (plugin discovery, seed routines, at-rest
    backfills, bloom-filter load, intel refresh) never runs during tests.
    """
    from httpx import ASGITransport, AsyncClient

    import main
    from database import get_db

    async def _override_get_db():
        yield db_session

    main.app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
    main.app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def make_user(db_session) -> Callable:
    """Factory that inserts a real ``User`` row into the test session.

    Usage::

        admin = await make_user(role="admin")
        op = await make_user(role="operator", username="alice")
    """
    from auth.password import get_password_hash
    from models.user import User, UserRole

    created: list[User] = []

    async def _make(
        role: str = "operator",
        password: str = "Sup3rSecret!pw",
        **overrides,
    ) -> User:
        role_enum = role if isinstance(role, UserRole) else UserRole(role)
        suffix = uuid.uuid4().hex[:8]
        fields = dict(
            id=str(uuid.uuid4()),
            username=f"user_{suffix}",
            email=f"{suffix}@test.local",
            hashed_password=get_password_hash(password),
            full_name="Test User",
            role=role_enum,
            is_active=True,
        )
        fields.update(overrides)
        user = User(**fields)
        db_session.add(user)
        await db_session.flush()
        # Re-load with the same eager options production's get_current_user
        # uses (selectinload(groups); recovery_codes is lazy="selectin" so it
        # loads on the query). Without this, serializing a UserResponse would
        # trip a lazy-load outside the async context (MissingGreenlet).
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        user = (
            await db_session.execute(
                select(User).where(User.id == user.id).options(selectinload(User.groups))
            )
        ).scalar_one()
        created.append(user)
        return user

    return _make


@pytest.fixture
def authenticate_as() -> Callable:
    """Return a helper that installs a ``get_current_user`` override so
    subsequent requests through ``client`` are authenticated as ``user``.

    Overriding the dependency (rather than minting a real JWT) keeps tests
    fast and sidesteps Redis (blacklist lookups) and the last-active
    middleware. ``require_roles(...)`` and ``get_current_active_user`` both
    resolve through ``get_current_user``, so role-gated routes still enforce
    correctly against the injected user.
    """
    import main
    from auth.dependencies import get_current_user

    def _auth(user) -> None:
        async def _override():
            return user

        main.app.dependency_overrides[get_current_user] = _override

    yield _auth
    main.app.dependency_overrides.pop(get_current_user, None)
