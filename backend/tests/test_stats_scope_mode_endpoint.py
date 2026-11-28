"""The stats-scope-mode admin setting over HTTP: who may read and change it,
that it persists and is audited, and that it changes what an unassigned
operator's dashboard shows (platform-wide counts with identifiers stripped
in global mode; only their own engagements in scoped mode)."""

from __future__ import annotations

import pytest
from sqlalchemy import delete, select

from tests.test_authz_boundaries import _make_engagement, _make_finding

URL = "/admin/settings/stats-scope-mode"


@pytest.fixture
async def clean_mode(db_session):
    from auth.rbac import _STATS_SCOPE_MODE_KEY
    from models.auth_settings import AuthSetting

    async def wipe():
        await db_session.execute(delete(AuthSetting).where(AuthSetting.key == _STATS_SCOPE_MODE_KEY))
        await db_session.commit()
    await wipe()
    yield
    await wipe()


async def test_admin_sets_mode_and_it_persists(client, db_session, make_user, authenticate_as, clean_mode):
    from auth.rbac import _STATS_SCOPE_MODE_KEY
    from models.auth_settings import AuthSetting
    from models.discussion import ActivityLog

    admin = await make_user(role="admin")
    authenticate_as(admin)
    assert (await client.get(URL)).json() == {"mode": "global"}, "unset defaults to global"

    r = await client.put(URL, json={"mode": "  Scoped "})
    assert r.status_code == 200 and r.json() == {"mode": "scoped"}
    assert (await client.get(URL)).json() == {"mode": "scoped"}
    # Second write updates the same row.
    assert (await client.put(URL, json={"mode": "global"})).json() == {"mode": "global"}
    db_session.expunge_all()
    rows = (await db_session.execute(select(AuthSetting).where(AuthSetting.key == _STATS_SCOPE_MODE_KEY))).scalars().all()
    assert [(r.value, r.updated_by) for r in rows] == [("global", admin.id)]
    logs = (await db_session.execute(select(ActivityLog.details).where(
        ActivityLog.resource_id == _STATS_SCOPE_MODE_KEY, ActivityLog.user_id == admin.id))).scalars().all()
    assert sorted(logs) == ["Stats scope mode set to 'global'", "Stats scope mode set to 'scoped'"]


@pytest.mark.parametrize("mode", ["everything", "", "x" * 17])
async def test_invalid_mode_is_refused(client, make_user, authenticate_as, clean_mode, mode):
    authenticate_as(await make_user(role="admin"))
    assert (await client.put(URL, json={"mode": mode})).status_code == 422
    assert (await client.get(URL)).json() == {"mode": "global"}


async def test_only_write_admins_change_it(client, make_user, authenticate_as, clean_mode):
    authenticate_as(await make_user(role="read_only_admin"))
    assert (await client.get(URL)).status_code == 200
    assert (await client.put(URL, json={"mode": "scoped"})).status_code == 403
    for role in ("team_lead", "operator"):
        authenticate_as(await make_user(role=role))
        assert (await client.get(URL)).status_code == 403
        assert (await client.put(URL, json={"mode": "scoped"})).status_code == 403
    authenticate_as(await make_user(role="admin"))
    assert (await client.get(URL)).json() == {"mode": "global"}


async def test_mode_changes_an_unassigned_operators_dashboard(client, db_session, make_user, authenticate_as, clean_mode):
    eng = await _make_engagement(db_session)
    finding = await _make_finding(db_session, eng)  # HIGH + OPEN, so it's a "top finding"
    await db_session.commit()
    admin, op = await make_user(role="admin"), await make_user(role="operator")

    async def operator_stats():
        authenticate_as(op)
        r = await client.get("/analytics/dashboard-stats")
        assert r.status_code == 200, r.text
        return r.json()

    stats = await operator_stats()  # global (default)
    assert stats["findings"]["total"] >= 1
    tops = [t for t in stats["top_findings"] if t["id"] == finding.id]
    assert tops and tops[0]["title"] is None and tops[0]["engagement_name"] is None, \
        "global mode counts everything but strips identifiers"

    authenticate_as(admin)
    assert (await client.put(URL, json={"mode": "scoped"})).status_code == 200
    stats = await operator_stats()
    assert stats["findings"]["total"] == 0 and stats["top_findings"] == [], \
        "scoped mode shows only the operator's own engagements"
