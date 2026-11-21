"""Regression: a fresh install seeds ``EVIDENCE_EDIT`` into the right
default engagement roles.

The seeder once granted Engagement Lead and Operator ``EVIDENCE_CREATE``
and ``EVIDENCE_DELETE`` but never ``EVIDENCE_EDIT``, so a non-admin could
upload evidence but not edit its description, report toggle or marking.
Engagement Lead gets EDIT and EDIT_ANY; Operator gets EDIT (own) only;
Observer neither. Runs the real seeder (and its revisions) against the
test database and reads the roles back.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from sqlalchemy import delete, select

ROLES = ("Engagement Lead", "Operator", "Observer")


@pytest.fixture
async def seeded(db_session, monkeypatch):
    import seed_permissions
    from models.engagement_role import EngagementRole
    from models.permission import EngagementRolePermissions

    # Start from a fresh install's state for these roles (rolled back after).
    ids = select(EngagementRole.id).where(EngagementRole.name.in_(ROLES))
    await db_session.execute(delete(EngagementRolePermissions).where(EngagementRolePermissions.role_id.in_(ids)))
    await db_session.execute(delete(EngagementRole).where(EngagementRole.name.in_(ROLES)))

    @asynccontextmanager
    async def _session():
        yield db_session
    monkeypatch.setattr(seed_permissions, "AsyncSessionLocal", _session)
    await seed_permissions.seed_default_groups_and_roles()

    rows = (await db_session.execute(
        select(EngagementRole.name, EngagementRolePermissions.permissions)
        .join(EngagementRolePermissions, EngagementRolePermissions.role_id == EngagementRole.id)
        .where(EngagementRole.name.in_(ROLES))
    )).all()
    return {name: set(perms) for name, perms in rows}


async def test_engagement_lead_can_edit_any_evidence(seeded):
    assert {"evidence_edit", "evidence_edit_any"} <= seeded["Engagement Lead"]


async def test_operator_edits_own_evidence_only(seeded):
    assert "evidence_edit" in seeded["Operator"]
    assert "evidence_edit_any" not in seeded["Operator"]


async def test_observer_cannot_edit_evidence(seeded):
    assert not {"evidence_edit", "evidence_edit_any"} & seeded["Observer"]
