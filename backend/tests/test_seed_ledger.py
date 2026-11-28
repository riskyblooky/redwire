"""Startup seeding creates each built-in default at most once: one an admin
deleted stays deleted across restarts;
one failing seeder doesn't stop the others."""

from __future__ import annotations

import contextlib
import json

import pytest
from sqlalchemy import select

import seed_defaults
import seed_permissions
from models.auth_settings import AuthSetting
from models.configurable_type import ConfigurableType
from models.finding import Tag
from models.group import Group


@pytest.fixture
def same_session(db_session, monkeypatch):
    @contextlib.asynccontextmanager
    async def _session():
        yield db_session
    monkeypatch.setattr(seed_defaults, "AsyncSessionLocal", _session)
    monkeypatch.setattr(seed_permissions, "AsyncSessionLocal", _session, raising=False)
    return db_session


async def _ledger(db, kind, keys=None):
    row = await db.get(AuthSetting, f"seeded_defaults:{kind}")
    if keys is None:
        if row is not None:
            await db.delete(row)
    elif row is None:
        db.add(AuthSetting(key=f"seeded_defaults:{kind}", value=json.dumps(keys), is_encrypted=False))
    else:
        row.value = json.dumps(keys)
    await db.flush()


async def test_deleted_default_tag_stays_deleted(same_session):
    db = same_session
    first = seed_defaults._DEFAULT_TAGS[0]
    await _ledger(db, "tags", [])                       # nothing seeded yet
    await seed_defaults.seed_tags()
    tag = (await db.execute(select(Tag).where(Tag.name == first["name"],
                                              Tag.entity_type == first.get("entity_type", "finding")))).scalars().first()
    assert tag is not None
    await db.delete(tag)
    await db.flush()

    assert await seed_defaults.seed_tags() == 0         # the restart doesn't bring it back
    assert (await db.execute(select(Tag).where(Tag.name == first["name"]))).scalars().first() is None


async def test_existing_install_records_defaults_without_recreating(same_session):
    db = same_session
    ct = seed_defaults._DEFAULT_CONFIGURABLE_TYPES[0]
    for row in (await db.execute(select(ConfigurableType).where(
            ConfigurableType.category == ct["category"], ConfigurableType.name == ct["name"]))).scalars():
        await db.delete(row)
    await db.flush()
    # An existing install: some types exist (here one non-default), no ledger yet.
    db.add(ConfigurableType(category="asset", name="Custom Admin Type", color="#000000", sort_order=99))
    await db.flush()
    await _ledger(db, "configurable_types", None)
    assert await seed_defaults.seed_configurable_types() == 0
    stored = json.loads((await db.get(AuthSetting, "seeded_defaults:configurable_types")).value)
    assert f'{ct["category"]}|{ct["name"]}' in stored


async def test_one_failing_seeder_does_not_stop_the_rest(monkeypatch):
    ran = []

    async def boom():
        raise RuntimeError("bad data")

    async def ok():
        ran.append(1)
        return 0
    # Every seeder but the failing one is stubbed: a real one would open
    # AsyncSessionLocal() on the app (dev) database.
    for name in ("seed_configurable_types", "sync_template_categories_to_configurable_types",
                 "seed_finding_templates", "seed_testcase_templates", "seed_system_widgets"):
        monkeypatch.setattr(seed_defaults, name, ok)
    monkeypatch.setattr(seed_defaults, "seed_tags", boom)
    monkeypatch.setattr(seed_defaults, "seed_skill_taxonomy", lambda: _pair())
    monkeypatch.setattr(seed_defaults, "seed_default_report_theme", lambda: _false())
    monkeypatch.setattr(seed_defaults, "seed_default_report_layout", lambda: _false())
    await seed_defaults.seed_all_defaults()
    assert len(ran) == 5


async def _pair():
    return (0, 0)


async def _false():
    return False


async def test_deleted_non_system_group_stays_deleted_system_group_returns(same_session):
    db = same_session
    await _ledger(db, "groups", ["Team Leads", "Read-Only Users", "Default"])
    for name in ("Read-Only Users", "Default"):
        g = (await db.execute(select(Group).where(Group.name == name))).scalars().first()
        if g is not None:
            await db.delete(g)
    await db.flush()
    await seed_permissions.seed_default_groups_and_roles()
    names = {g.name for g in (await db.execute(select(Group))).scalars()}
    assert "Default" in names and "Read-Only Users" not in names
